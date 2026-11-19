import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal
from uuid import uuid4

from computer_agent.agent.task_state import (
    AgentState,
    ProposedAction,
    TaskRequest,
    TaskResult,
    TaskStep,
)
from computer_agent.computer.actions import AcquiredRecord


RunStatus = Literal[
    "running",
    "completed",
    "step_limit_reached",
    "loop_detected",
    "timed_out",
    "terminated",
    "failed",
]
ApprovalStatus = Literal["pending", "approved", "denied"]


@dataclass(frozen=True)
class RunSnapshot:
    request: TaskRequest
    state: AgentState
    page_url: str
    status: RunStatus


@dataclass(frozen=True)
class VerifiedProcedure:
    name: str
    source_run_id: str
    start_page: str
    actions: tuple[ProposedAction, ...]


@dataclass(frozen=True)
class ArtifactEntry:
    artifact_id: str
    run_id: str
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ApprovalEntry:
    approval_id: str
    run_id: str
    action: dict[str, object]
    status: ApprovalStatus
    created_at: str
    resolved_at: str | None


class SQLiteMemory:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'running',
                            'completed',
                            'step_limit_reached',
                            'loop_detected',
                            'timed_out',
                            'terminated',
                            'failed'
                        )
                    ),
                    reason TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY REFERENCES task_runs(run_id),
                    page_url TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_steps (
                    run_id TEXT NOT NULL REFERENCES task_runs(run_id),
                    number INTEGER NOT NULL,
                    step_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, number)
                );

                CREATE TABLE IF NOT EXISTS acquired_records (
                    run_id TEXT NOT NULL REFERENCES task_runs(run_id),
                    record_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, record_id)
                );

                CREATE TABLE IF NOT EXISTS verified_procedures (
                    procedure_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    source_run_id TEXT NOT NULL REFERENCES task_runs(run_id),
                    start_page TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES task_runs(run_id),
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES task_runs(run_id),
                    action_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'approved', 'denied')
                    ),
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                """
            )
            task_runs_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'task_runs'"
            ).fetchone()["sql"]
            if "'terminated'" not in task_runs_sql or "'failed'" not in task_runs_sql:
                connection.execute("PRAGMA foreign_keys = OFF")
                connection.execute(
                    """
                    CREATE TABLE task_runs_new (
                        run_id TEXT PRIMARY KEY,
                        request_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN (
                                'running',
                                'completed',
                                'step_limit_reached',
                                'loop_detected',
                                'timed_out',
                                'terminated',
                                'failed'
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
                    INSERT INTO task_runs_new
                    SELECT run_id, request_json, status, reason, result_json,
                           created_at, updated_at
                    FROM task_runs
                    """
                )
                connection.execute("DROP TABLE task_runs")
                connection.execute(
                    "ALTER TABLE task_runs_new RENAME TO task_runs"
                )

    def create_run(self, run_id: str, request: TaskRequest) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO task_runs (
                    run_id, request_json, status, created_at, updated_at
                ) VALUES (?, ?, 'running', ?, ?)
                """,
                (run_id, json.dumps(asdict(request)), now, now),
            )

    def set_running(self, run_id: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = 'running', reason = NULL, result_json = NULL,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (_now(), run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task run {run_id!r}.")

    def save_progress(
        self,
        run_id: str,
        state: AgentState,
        page_url: str,
    ) -> None:
        with self._connection() as connection:
            self._write_progress(connection, run_id, state, page_url, _now())

    def finish_run(
        self,
        run_id: str,
        result: TaskResult,
        state: AgentState | None = None,
        page_url: str | None = None,
    ) -> None:
        if (state is None) != (page_url is None):
            raise ValueError("A final checkpoint requires both state and page URL.")
        now = _now()
        with self._connection() as connection:
            if state is not None and page_url is not None:
                self._write_progress(connection, run_id, state, page_url, now)
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = ?, reason = ?, result_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    result.status,
                    result.reason,
                    json.dumps(asdict(result)),
                    now,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task run {run_id!r}.")

    def fail_run(self, run_id: str, reason: str) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE task_runs
                SET status = 'failed', reason = ?, result_json = NULL,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (reason, _now(), run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task run {run_id!r}.")

    def _write_progress(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        state: AgentState,
        page_url: str,
        now: str,
    ) -> None:
        state_json = json.dumps(_serialize_state(state))
        for step in state.steps:
            serialized_step = json.dumps(asdict(step))
            existing = connection.execute(
                """
                SELECT step_json FROM execution_steps
                WHERE run_id = ? AND number = ?
                """,
                (run_id, step.number),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO execution_steps (run_id, number, step_json)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, step.number, serialized_step),
                )
            elif json.loads(existing["step_json"]) != json.loads(serialized_step):
                raise ValueError(
                    f"Execution step {step.number} conflicts with saved history."
                )

        for record in state.records_by_id.values():
            serialized_record = json.dumps(asdict(record))
            existing = connection.execute(
                """
                SELECT record_json FROM acquired_records
                WHERE run_id = ? AND record_id = ?
                """,
                (run_id, record.record_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO acquired_records (run_id, record_id, record_json)
                    VALUES (?, ?, ?)
                    """,
                    (run_id, record.record_id, serialized_record),
                )
            elif json.loads(existing["record_json"]) != json.loads(serialized_record):
                raise ValueError(
                    f"Acquired record {record.record_id!r} conflicts with saved data."
                )

        connection.execute(
            """
            INSERT INTO checkpoints (run_id, page_url, state_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                page_url = excluded.page_url,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (run_id, page_url, state_json, now),
        )
        cursor = connection.execute(
            "UPDATE task_runs SET updated_at = ? WHERE run_id = ?",
            (now, run_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"Unknown task run {run_id!r}.")

    def load_run(self, run_id: str) -> RunSnapshot:
        with self._connection() as connection:
            run = connection.execute(
                """
                SELECT request_json, status FROM task_runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(f"Unknown task run {run_id!r}.")
            checkpoint = connection.execute(
                """
                SELECT page_url, state_json FROM checkpoints WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if checkpoint is None:
                raise ValueError(f"Task run {run_id!r} has no resumable checkpoint.")

        request = TaskRequest(**json.loads(run["request_json"]))
        state = _deserialize_state(
            run_id,
            request,
            json.loads(checkpoint["state_json"]),
        )
        return RunSnapshot(
            request=request,
            state=state,
            page_url=checkpoint["page_url"],
            status=run["status"],
        )

    def save_verified_procedure(self, run_id: str, name: str) -> VerifiedProcedure:
        if not name.strip():
            raise ValueError("A procedure name is required.")
        with self._connection() as connection:
            run = connection.execute(
                """
                SELECT request_json, status FROM task_runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if run is None:
                raise KeyError(f"Unknown task run {run_id!r}.")
            if run["status"] != "completed":
                raise ValueError("Only completed task runs can become procedures.")
            rows = connection.execute(
                """
                SELECT step_json FROM execution_steps
                WHERE run_id = ? ORDER BY number
                """,
                (run_id,),
            ).fetchall()
            actions = [
                {
                    "name": step["action"],
                    "target": step["target"],
                    "role": step.get("role"),
                }
                for row in rows
                if (step := json.loads(row["step_json"]))["action"]
                in {"fill", "click", "extract"}
            ]
            if not actions:
                raise ValueError("The completed run has no replayable actions.")

            request = json.loads(run["request_json"])
            procedure_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO verified_procedures (
                    procedure_id, name, source_run_id, start_page, actions_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    procedure_id,
                    name,
                    run_id,
                    request["start_page"],
                    json.dumps(actions),
                    _now(),
                ),
            )

        return VerifiedProcedure(
            name=name,
            source_run_id=run_id,
            start_page=request["start_page"],
            actions=tuple(
                ProposedAction(**action)
                for action in actions
            ),
        )

    def load_procedure(self, name: str) -> VerifiedProcedure:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT procedure_id, source_run_id, start_page, actions_json
                FROM verified_procedures WHERE name = ?
                """,
                (name,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown verified procedure {name!r}.")
        return VerifiedProcedure(
            name=name,
            source_run_id=row["source_run_id"],
            start_page=row["start_page"],
            actions=tuple(
                ProposedAction(**action)
                for action in json.loads(row["actions_json"])
            ),
        )

    def request_approval(
        self,
        run_id: str,
        action: dict[str, object],
    ) -> ApprovalEntry:
        approval_id = str(uuid4())
        created_at = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO approval_requests (
                    approval_id, run_id, action_json, status, created_at
                ) VALUES (?, ?, ?, 'pending', ?)
                """,
                (approval_id, run_id, json.dumps(action), created_at),
            )
        return ApprovalEntry(
            approval_id=approval_id,
            run_id=run_id,
            action=action,
            status="pending",
            created_at=created_at,
            resolved_at=None,
        )

    def resolve_approval(self, approval_id: str, approved: bool) -> ApprovalEntry:
        status: ApprovalStatus = "approved" if approved else "denied"
        resolved_at = _now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET status = ?, resolved_at = ?
                WHERE approval_id = ? AND status = 'pending'
                """,
                (status, resolved_at, approval_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    f"Approval {approval_id!r} is missing or already resolved."
                )
            row = connection.execute(
                """
                SELECT run_id, action_json, created_at, resolved_at, status
                FROM approval_requests WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        return ApprovalEntry(
            approval_id=approval_id,
            run_id=row["run_id"],
            action=json.loads(row["action_json"]),
            status=row["status"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )

    def record_artifact(self, entry: ArtifactEntry) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, run_id, relative_path, media_type, size_bytes,
                    sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.artifact_id,
                    entry.run_id,
                    entry.relative_path,
                    entry.media_type,
                    entry.size_bytes,
                    entry.sha256,
                    _now(),
                ),
            )

    def list_artifacts(self, run_id: str) -> tuple[ArtifactEntry, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT artifact_id, run_id, relative_path, media_type,
                       size_bytes, sha256
                FROM artifacts WHERE run_id = ? ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
        return tuple(ArtifactEntry(**dict(row)) for row in rows)

    def list_approvals(self, run_id: str) -> tuple[ApprovalEntry, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT approval_id, run_id, action_json, status, created_at,
                       resolved_at
                FROM approval_requests WHERE run_id = ? ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
        return tuple(
            ApprovalEntry(
                approval_id=row["approval_id"],
                run_id=row["run_id"],
                action=json.loads(row["action_json"]),
                status=row["status"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
            )
            for row in rows
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _serialize_state(state: AgentState) -> dict[str, object]:
    return {
        "steps": [asdict(step) for step in state.steps],
        "pages_visited": state.pages_visited,
        "extracted_pages": sorted(state.extracted_pages),
        "records": [asdict(record) for record in state.records_by_id.values()],
        "query_filled": state.query_filled,
        "search_submitted": state.search_submitted,
    }


def _deserialize_state(
    run_id: str,
    request: TaskRequest,
    data: dict[str, object],
) -> AgentState:
    steps = [TaskStep(**step) for step in data["steps"]]
    records = [
        AcquiredRecord(**record)
        for record in data["records"]
    ]
    return AgentState(
        request=request,
        run_id=run_id,
        steps=steps,
        pages_visited=list(data["pages_visited"]),
        extracted_pages=set(data["extracted_pages"]),
        records_by_id={record.record_id: record for record in records},
        query_filled=data["query_filled"],
        search_submitted=data["search_submitted"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
