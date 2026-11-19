import asyncio
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Literal
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from computer_agent.agent.control import TaskControl
from computer_agent.agent.planner import HeuristicPlanner, Planner
from computer_agent.agent.runtime import replay_procedure, run_task
from computer_agent.agent.task_state import TaskRequest, TaskResult
from computer_agent.integrations.adapters import (
    DEFAULT_DESTINATION,
    QuarantineExporter,
)
from computer_agent.integrations.web_search import (
    WebSearchError,
    WebSearchRequest,
    WebSearchResponse,
    search_web,
)
from computer_agent.intelligence.model_provider import GroqProvider, OllamaProvider
from computer_agent.memory.artifacts import ArtifactManager, DEFAULT_ARTIFACT_ROOT
from computer_agent.memory.store import RunSummary, SQLiteMemory, VerifiedProcedure


PlannerName = Literal["site-rules", "heuristic", "ollama", "groq", "procedure-replay"]
SubmissionPlannerName = Literal["site-rules", "heuristic", "ollama", "groq"]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_DB = PROJECT_ROOT / "artifacts" / "memory.sqlite3"
WEB_DIST_DIR = PROJECT_ROOT / "web" / "dist"


class TaskSubmission(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    max_steps: int = Field(default=12, ge=1, le=20)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)
    start_page: str = "index.html"
    planner: SubmissionPlannerName = "site-rules"
    model: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_request(self) -> "TaskSubmission":
        TaskRequest(
            query=self.query,
            max_steps=self.max_steps,
            timeout_seconds=self.timeout_seconds,
            start_page=self.start_page,
        )
        return self

    def task_request(self) -> TaskRequest:
        return TaskRequest(
            query=self.query,
            max_steps=self.max_steps,
            timeout_seconds=self.timeout_seconds,
            start_page=self.start_page,
        )


class SaveProcedureRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ReplayProcedureRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    max_steps: int = Field(default=12, ge=1, le=20)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)


class QuarantineExportRequest(BaseModel):
    destination: str = Field(default=DEFAULT_DESTINATION, min_length=1, max_length=64)


@dataclass
class ManagedTask:
    task_id: str
    request: TaskRequest
    planner_name: PlannerName
    control: TaskControl
    runner: asyncio.Task[None]
    result: TaskResult | None = None
    error: str | None = None


class TaskManager:
    def __init__(
        self,
        memory: SQLiteMemory,
        artifacts: ArtifactManager | None = None,
    ) -> None:
        self.memory = memory
        self.artifacts = artifacts or ArtifactManager(memory)
        self.exporter = QuarantineExporter(memory, self.artifacts)
        self._tasks: dict[str, ManagedTask] = {}

    def submit(self, submission: TaskSubmission) -> ManagedTask:
        task_id = str(uuid4())
        request = submission.task_request()
        control = TaskControl()
        control.publish("status", {"status": "running"})
        planner = _make_planner(submission)
        runner = asyncio.create_task(
            self._run(task_id, request, planner, control),
            name=f"computer-agent-{task_id}",
        )
        managed = ManagedTask(
            task_id=task_id,
            request=request,
            planner_name=submission.planner,
            control=control,
            runner=runner,
        )
        self._tasks[task_id] = managed
        return managed

    def submit_replay(
        self,
        procedure_name: str,
        replay_request: ReplayProcedureRequest,
    ) -> ManagedTask:
        procedure = self.memory.load_procedure(procedure_name)
        request = TaskRequest(
            query=replay_request.query,
            max_steps=replay_request.max_steps,
            timeout_seconds=replay_request.timeout_seconds,
            start_page=procedure.start_page,
        )
        task_id = str(uuid4())
        control = TaskControl()
        control.publish("status", {"status": "running"})
        runner = asyncio.create_task(
            self._run_replay(task_id, procedure, request, control),
            name=f"computer-agent-replay-{task_id}",
        )
        managed = ManagedTask(
            task_id=task_id,
            request=request,
            planner_name="procedure-replay",
            control=control,
            runner=runner,
        )
        self._tasks[task_id] = managed
        return managed

    async def _run(
        self,
        task_id: str,
        request: TaskRequest,
        planner: Planner | None,
        control: TaskControl,
    ) -> None:
        try:
            result = await run_task(
                request,
                planner=planner,
                memory=self.memory,
                run_id=task_id,
                control=control,
            )
            managed = self._tasks[task_id]
            managed.result = result
            control.publish("result", asdict(result))
        except Exception as error:
            self._tasks[task_id].error = str(error)
            try:
                self.memory.fail_run(task_id, str(error))
            except Exception as persistence_error:
                self._tasks[task_id].error = (
                    f"{error}; additionally, failed to persist task failure: "
                    f"{persistence_error}"
                )
            control.publish("error", {"message": str(error)})
        finally:
            managed = self._tasks[task_id]
            control.publish("status", {"status": self._status(managed)})
            control.mark_finished()

    async def _run_replay(
        self,
        task_id: str,
        procedure: VerifiedProcedure,
        request: TaskRequest,
        control: TaskControl,
    ) -> None:
        try:
            result = await replay_procedure(
                procedure,
                request,
                memory=self.memory,
                run_id=task_id,
                control=control,
            )
            managed = self._tasks[task_id]
            managed.result = result
            control.publish("result", asdict(result))
        except Exception as error:
            self._tasks[task_id].error = str(error)
            try:
                self.memory.fail_run(task_id, str(error))
            except Exception as persistence_error:
                self._tasks[task_id].error = (
                    f"{error}; additionally, failed to persist task failure: "
                    f"{persistence_error}"
                )
            control.publish("error", {"message": str(error)})
        finally:
            managed = self._tasks[task_id]
            control.publish("status", {"status": self._status(managed)})
            control.mark_finished()

    def get(self, task_id: str) -> ManagedTask:
        try:
            return self._tasks[task_id]
        except KeyError as error:
            raise KeyError(f"Unknown task {task_id!r}.") from error

    def inspect(self, task_id: str) -> dict[str, object]:
        managed = self._tasks.get(task_id)
        if managed is not None:
            return self.view(managed)
        summary = self.memory.get_run(task_id)
        return self.view_summary(summary)

    def list_views(self, limit: int = 25) -> list[dict[str, object]]:
        views_by_id: dict[str, dict[str, object]] = {}
        ordered_ids: list[str] = []

        for managed in reversed(list(self._tasks.values())):
            views_by_id[managed.task_id] = self.view(managed)
            ordered_ids.append(managed.task_id)

        for summary in self.memory.list_runs(limit=limit):
            if summary.run_id not in views_by_id:
                views_by_id[summary.run_id] = self.view_summary(summary)
                ordered_ids.append(summary.run_id)

        return [views_by_id[task_id] for task_id in ordered_ids[:limit]]

    def pause(self, task_id: str) -> ManagedTask:
        managed = self._active_task(task_id)
        managed.control.pause()
        status = "paused" if managed.control.paused else "pausing"
        managed.control.publish("status", {"status": status})
        return managed

    def resume(self, task_id: str) -> ManagedTask:
        managed = self._active_task(task_id)
        managed.control.resume()
        managed.control.publish("status", {"status": "running"})
        return managed

    def terminate(self, task_id: str) -> ManagedTask:
        managed = self._active_task(task_id)
        managed.control.stop()
        managed.control.publish("status", {"status": "stopping"})
        return managed

    def view(self, managed: ManagedTask) -> dict[str, object]:
        return {
            "task_id": managed.task_id,
            "status": self._status(managed),
            "query": managed.request.query,
            "start_page": managed.request.start_page,
            "planner": managed.planner_name,
            "latest_observation": managed.control.latest_observation,
            "result": None if managed.result is None else asdict(managed.result),
            "error": managed.error,
        }

    @staticmethod
    def view_summary(summary: RunSummary) -> dict[str, object]:
        return {
            "task_id": summary.run_id,
            "status": summary.status,
            "query": summary.request.query,
            "start_page": summary.request.start_page,
            "planner": "persisted",
            "latest_observation": None,
            "result": summary.result,
            "error": summary.reason if summary.status == "failed" else None,
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
        }

    def _active_task(self, task_id: str) -> ManagedTask:
        managed = self.get(task_id)
        if managed.runner.done() or managed.control.finished:
            raise ValueError(f"Task {task_id!r} is no longer active.")
        if managed.control.stopping:
            raise ValueError(f"Task {task_id!r} is already stopping.")
        return managed

    @staticmethod
    def _status(managed: ManagedTask) -> str:
        if managed.error is not None:
            return "failed"
        if managed.result is not None:
            return managed.result.status
        if managed.control.stopping:
            return "stopping"
        if managed.control.paused:
            return "paused"
        if managed.control.pause_requested:
            return "pausing"
        return "running"


def _build_api_router(manager: TaskManager) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/research", response_model=WebSearchResponse)
    async def research(request_data: WebSearchRequest) -> WebSearchResponse:
        try:
            return await search_web(request_data.query)
        except WebSearchError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.get("/tasks")
    async def list_tasks(limit: int = 25) -> dict[str, object]:
        return {"tasks": manager.list_views(limit=limit)}

    @router.post("/tasks", status_code=202)
    async def submit_task(submission: TaskSubmission) -> dict[str, object]:
        try:
            managed = manager.submit(submission)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return manager.view(managed)

    @router.get("/tasks/{task_id}")
    async def inspect_task(task_id: str) -> dict[str, object]:
        try:
            return manager.inspect(task_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/tasks/{task_id}/pause")
    async def pause_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.pause)

    @router.post("/tasks/{task_id}/resume")
    async def resume_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.resume)

    @router.post("/tasks/{task_id}/terminate")
    async def terminate_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.terminate)

    @router.get("/tasks/{task_id}/events")
    async def task_events(
        task_id: str,
        request: Request,
        last_event_id: int = Header(default=0, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        try:
            managed = manager.get(task_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        async def event_stream() -> AsyncIterator[str]:
            async for event in managed.control.events(last_event_id):
                if await request.is_disconnected():
                    break
                if event is None:
                    yield ": keep-alive\n\n"
                else:
                    yield (
                        f"id: {event.event_id}\n"
                        f"event: {event.event}\n"
                        f"data: {json.dumps(event.data)}\n\n"
                    )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/tasks/{task_id}/save-procedure", status_code=201)
    async def save_procedure(
        task_id: str,
        payload: SaveProcedureRequest,
    ) -> dict[str, object]:
        try:
            procedure = manager.memory.save_verified_procedure(
                task_id,
                payload.name.strip(),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=409,
                detail=f"A verified procedure named {payload.name.strip()!r} already exists.",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _serialize_procedure(procedure)

    @router.get("/procedures")
    async def list_procedures() -> dict[str, object]:
        procedures = manager.memory.list_procedures()
        return {"procedures": [_serialize_procedure(p) for p in procedures]}

    @router.post("/procedures/{name}/replay", status_code=202)
    async def replay_saved_procedure(
        name: str,
        payload: ReplayProcedureRequest,
    ) -> dict[str, object]:
        try:
            managed = manager.submit_replay(name, payload)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return manager.view(managed)

    @router.get("/tasks/{task_id}/artifacts")
    async def list_task_artifacts(task_id: str) -> dict[str, object]:
        try:
            manager.inspect(task_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        entries = manager.memory.list_artifacts(task_id)
        return {"artifacts": [asdict(entry) for entry in entries]}

    @router.post("/tasks/{task_id}/export", status_code=201)
    async def export_task_quarantine(
        task_id: str,
        payload: QuarantineExportRequest | None = None,
    ) -> dict[str, object]:
        destination = (
            DEFAULT_DESTINATION if payload is None else payload.destination
        )
        try:
            export_result = manager.exporter.export_run(task_id, destination)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "run_id": export_result.run_id,
            "destination": export_result.destination,
            "quarantine_status": export_result.quarantine_status,
            "exported_at": export_result.exported_at,
            "record_count": export_result.record_count,
            "payload_artifact": asdict(export_result.payload_artifact),
            "manifest_artifact": asdict(export_result.manifest_artifact),
            "manifest": export_result.manifest,
        }

    @router.get("/artifacts/{artifact_id}")
    async def read_artifact(artifact_id: str) -> dict[str, object]:
        try:
            entry = manager.memory.get_artifact(artifact_id)
            content_bytes = manager.artifacts.read_verified(entry)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        text_content = content_bytes.decode("utf-8", errors="replace")
        parsed_json: object | None = None
        if entry.media_type == "application/json":
            try:
                parsed_json = json.loads(text_content)
            except ValueError:
                parsed_json = None
        return {
            "artifact": asdict(entry),
            "verified": True,
            "content": text_content,
            "json": parsed_json,
        }

    return router


def create_app(
    memory_path: Path = DEFAULT_MEMORY_DB,
    artifact_root: Path | None = None,
    serve_frontend: bool = True,
) -> FastAPI:
    app = FastAPI(
        title="Computer Agent Control API",
        description="Local control interface for the bounded fixture-site agent.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    resolved_artifact_root = (
        artifact_root
        if artifact_root is not None
        else (
            DEFAULT_ARTIFACT_ROOT
            if memory_path == DEFAULT_MEMORY_DB
            else Path(memory_path).resolve().parent / "workspace"
        )
    )
    memory = SQLiteMemory(memory_path)
    artifacts = ArtifactManager(memory, root=resolved_artifact_root)
    manager = TaskManager(memory, artifacts=artifacts)
    app.state.task_manager = manager

    router = _build_api_router(manager)
    app.include_router(router)
    app.include_router(router, prefix="/api")

    if serve_frontend and (WEB_DIST_DIR / "index.html").is_file():
        assets_dir = WEB_DIST_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="web-assets")

        @app.get("/", include_in_schema=False)
        async def serve_index() -> FileResponse:
            return FileResponse(WEB_DIST_DIR / "index.html")

    return app


def _serialize_procedure(procedure: VerifiedProcedure) -> dict[str, object]:
    return {
        "name": procedure.name,
        "source_run_id": procedure.source_run_id,
        "start_page": procedure.start_page,
        "action_count": len(procedure.actions),
        "actions": [asdict(action) for action in procedure.actions],
    }


def _control_response(
    manager: TaskManager,
    task_id: str,
    action: Callable[[str], ManagedTask],
) -> dict[str, object]:
    try:
        return manager.view(action(task_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def _make_planner(submission: TaskSubmission) -> Planner | None:
    if submission.planner == "heuristic":
        return HeuristicPlanner()
    if submission.planner == "ollama":
        return OllamaProvider(
            submission.model or "qwen2.5-coder:3b",
            timeout_seconds=submission.timeout_seconds,
        )
    if submission.planner == "groq":
        return GroqProvider(
            submission.model,
            timeout_seconds=submission.timeout_seconds,
        )
    return None


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
