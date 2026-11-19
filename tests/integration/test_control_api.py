import asyncio
import sqlite3

from fastapi.testclient import TestClient

from computer_agent.api.main import TaskManager, TaskSubmission, create_app
from computer_agent.memory.store import SQLiteMemory


def test_api_restricts_tasks_and_streams_progress(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "memory.sqlite3")) as client:
        rejected = client.post(
            "/tasks",
            json={"query": "electrician", "start_page": "../outside.html"},
        )
        assert rejected.status_code == 422

        submitted = client.post(
            "/tasks",
            json={"query": "electrician", "max_steps": 1},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]

        with client.stream("GET", f"/tasks/{task_id}/events") as response:
            assert response.status_code == 200
            events = "".join(response.iter_text())

        assert "event: observation" in events
        assert "event: result" in events
        inspected = client.get(f"/tasks/{task_id}")
        assert inspected.status_code == 200
        assert inspected.json()["status"] == "step_limit_reached"
        assert client.post(f"/tasks/{task_id}/pause").status_code == 409
        assert client.post(f"/tasks/{task_id}/resume").status_code == 409
        assert client.post(f"/tasks/{task_id}/terminate").status_code == 409


def test_tasks_can_pause_resume_and_terminate_at_safe_boundaries(tmp_path) -> None:
    async def run() -> None:
        memory = SQLiteMemory(tmp_path / "memory.sqlite3")
        manager = TaskManager(memory)
        paused = manager.submit(TaskSubmission(query="electrician"))
        manager.pause(paused.task_id)

        for _ in range(100):
            if manager.view(paused)["status"] == "paused":
                break
            await asyncio.sleep(0.05)
        assert manager.view(paused)["status"] == "paused"
        assert paused.control.latest_observation is not None
        manager.resume(paused.task_id)
        await paused.runner
        assert paused.result is not None
        assert paused.result.status == "completed"

        terminated = manager.submit(
            TaskSubmission(query="electrician", max_steps=12)
        )
        manager.terminate(terminated.task_id)
        await terminated.runner
        assert terminated.result is not None
        assert terminated.result.status == "terminated"
        assert memory.load_run(terminated.task_id).status == "terminated"

    asyncio.run(run())


def test_existing_memory_database_migrates_task_status_constraint(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE task_runs (
                run_id TEXT PRIMARY KEY,
                request_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'running',
                        'completed',
                        'step_limit_reached',
                        'loop_detected',
                        'timed_out'
                    )
                ),
                reason TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO task_runs
            VALUES ('legacy-run', '{}', 'running', NULL, NULL, 'now', 'now')
            """
        )

    SQLiteMemory(path)
    with sqlite3.connect(path) as connection:
        status = connection.execute(
            "SELECT status FROM task_runs WHERE run_id = 'legacy-run'"
        ).fetchone()[0]
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'task_runs'"
        ).fetchone()[0]

    assert status == "running"
    assert "'terminated'" in schema
    assert "'failed'" in schema
