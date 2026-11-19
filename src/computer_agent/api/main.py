import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import AsyncIterator, Callable, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from computer_agent.agent.control import TaskControl
from computer_agent.agent.planner import HeuristicPlanner, Planner
from computer_agent.agent.runtime import run_task
from computer_agent.agent.task_state import TaskRequest, TaskResult
from computer_agent.intelligence.model_provider import GroqProvider, OllamaProvider
from computer_agent.memory.store import SQLiteMemory


PlannerName = Literal["site-rules", "heuristic", "ollama", "groq"]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_DB = PROJECT_ROOT / "artifacts" / "memory.sqlite3"


class TaskSubmission(BaseModel):
    query: str = Field(min_length=1, max_length=100)
    max_steps: int = Field(default=12, ge=1, le=20)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)
    start_page: str = "index.html"
    planner: PlannerName = "site-rules"
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
    def __init__(self, memory: SQLiteMemory) -> None:
        self.memory = memory
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

    def get(self, task_id: str) -> ManagedTask:
        try:
            return self._tasks[task_id]
        except KeyError as error:
            raise KeyError(f"Unknown task {task_id!r}.") from error

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
            "planner": managed.planner_name,
            "latest_observation": managed.control.latest_observation,
            "result": None if managed.result is None else asdict(managed.result),
            "error": managed.error,
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


def create_app(memory_path: Path = DEFAULT_MEMORY_DB) -> FastAPI:
    app = FastAPI(
        title="Computer Agent Control API",
        description="Local control interface for the bounded fixture-site agent.",
        version="0.1.0",
    )
    manager = TaskManager(SQLiteMemory(memory_path))
    app.state.task_manager = manager

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/tasks", status_code=202)
    async def submit_task(submission: TaskSubmission) -> dict[str, object]:
        managed = manager.submit(submission)
        return manager.view(managed)

    @app.get("/tasks/{task_id}")
    async def inspect_task(task_id: str) -> dict[str, object]:
        try:
            return manager.view(manager.get(task_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/tasks/{task_id}/pause")
    async def pause_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.pause)

    @app.post("/tasks/{task_id}/resume")
    async def resume_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.resume)

    @app.post("/tasks/{task_id}/terminate")
    async def terminate_task(task_id: str) -> dict[str, object]:
        return _control_response(manager, task_id, manager.terminate)

    @app.get("/tasks/{task_id}/events")
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

    return app


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
