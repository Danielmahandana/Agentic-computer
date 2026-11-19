import asyncio
import sqlite3

import pytest

from computer_agent.agent.runtime import replay_procedure, resume_task, run_task
from computer_agent.agent.task_state import TaskRequest, TaskStep
from computer_agent.memory.artifacts import ArtifactManager
from computer_agent.memory.store import SQLiteMemory


def test_run_can_resume_and_save_replayable_procedure(tmp_path) -> None:
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    interrupted = asyncio.run(
        run_task(
            TaskRequest(query="electrician", max_steps=2),
            memory=memory,
        )
    )

    assert interrupted.status == "step_limit_reached"
    assert interrupted.run_id is not None
    checkpoint = memory.load_run(interrupted.run_id)
    assert checkpoint.status == "step_limit_reached"
    assert len(checkpoint.state.steps) == 2
    assert checkpoint.page_url in checkpoint.state.pages_visited
    with pytest.raises(ValueError, match="completed task runs"):
        memory.save_verified_procedure(interrupted.run_id, "electrician search")

    resumed = asyncio.run(
        resume_task(
            interrupted.run_id,
            memory,
            max_steps=12,
        )
    )

    assert resumed.status == "completed"
    assert [record.record_id for record in resumed.records] == ["job-001", "job-003"]
    assert resumed.run_id == interrupted.run_id

    procedure = memory.save_verified_procedure(
        interrupted.run_id,
        "local electrician search",
    )
    reopened_memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    loaded_procedure = reopened_memory.load_procedure("local electrician search")
    replayed = asyncio.run(
        replay_procedure(
            loaded_procedure,
            TaskRequest(query="electrician"),
            memory=reopened_memory,
        )
    )

    assert replayed.status == "completed"
    assert [record.record_id for record in replayed.records] == [
        "job-001",
        "job-003",
    ]
    assert replayed.run_id != procedure.source_run_id


def test_final_checkpoint_and_result_commit_atomically(tmp_path) -> None:
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    interrupted = asyncio.run(
        run_task(
            TaskRequest(query="electrician", max_steps=1),
            memory=memory,
        )
    )
    assert interrupted.run_id is not None
    before = memory.load_run(interrupted.run_id)
    before.state.steps.append(
        TaskStep(
            number=2,
            action="finish",
            target="task complete",
            url_before=before.page_url,
            url_after=before.page_url,
            result="Task completed.",
            duration_ms=0,
        )
    )
    completed = before.state.result("completed", "Task completed.")

    with sqlite3.connect(memory.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_completed_run
            BEFORE UPDATE OF status ON task_runs
            WHEN NEW.status = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'simulated final-write failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="simulated final-write failure"):
        memory.finish_run(
            interrupted.run_id,
            completed,
            before.state,
            before.page_url,
        )

    after = memory.load_run(interrupted.run_id)
    assert after.status == "step_limit_reached"
    assert len(after.state.steps) == 1


def test_artifacts_are_confined_and_hash_verified(tmp_path) -> None:
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    run_id = "artifact-test"
    memory.create_run(run_id, TaskRequest(query="electrician"))
    manager = ArtifactManager(memory, tmp_path / "workspace")

    entry = manager.save_bytes(
        run_id,
        "runs/demo/result.json",
        b'{"ok": true}',
        "application/json",
    )

    assert manager.read_verified(entry) == b'{"ok": true}'
    assert memory.list_artifacts(run_id) == (entry,)
    with pytest.raises(FileExistsError, match="already contains different data"):
        manager.save_bytes(
            run_id,
            "runs/demo/result.json",
            b'{"replacement": true}',
            "application/json",
        )
    with pytest.raises(ValueError, match="inside the artifact workspace"):
        manager.save_bytes(
            run_id,
            "../escape.json",
            b"not allowed",
            "application/json",
        )

    (tmp_path / "workspace" / "runs" / "demo" / "result.json").write_bytes(
        b'{"no": true}'
    )
    with pytest.raises(ValueError, match="hash"):
        manager.read_verified(entry)


def test_approval_requests_are_audited_and_single_use(tmp_path) -> None:
    memory = SQLiteMemory(tmp_path / "memory.sqlite3")
    run_id = "approval-test"
    memory.create_run(run_id, TaskRequest(query="electrician"))

    pending = memory.request_approval(
        run_id,
        {"action": "download", "target": "local fixture document"},
    )
    assert memory.list_approvals(run_id) == (pending,)

    resolved = memory.resolve_approval(pending.approval_id, approved=True)
    assert resolved.status == "approved"
    with pytest.raises(ValueError, match="already resolved"):
        memory.resolve_approval(pending.approval_id, approved=False)
