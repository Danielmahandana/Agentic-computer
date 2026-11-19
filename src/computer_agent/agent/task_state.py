from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from computer_agent.computer.actions import AcquiredRecord, DEMO_ROOT


TaskStatus = Literal[
    "completed",
    "step_limit_reached",
    "loop_detected",
    "timed_out",
    "terminated",
    "failed",
]
AgentActionName = Literal["fill", "click", "extract", "finish"]


@dataclass(frozen=True)
class TaskRequest:
    query: str
    max_steps: int = 12
    timeout_seconds: float = 30.0
    start_page: str = "index.html"

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("A non-empty search query is required.")
        if len(self.query) > 100:
            raise ValueError("Search queries cannot exceed 100 characters.")
        if not 1 <= self.max_steps <= 20:
            raise ValueError("max_steps must be between 1 and 20.")
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be greater than 0 and at most 60.")
        if "\\" in self.start_page:
            raise ValueError("start_page must use a relative POSIX-style path.")
        relative_path = PurePosixPath(self.start_page)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("start_page must stay inside the local demo site.")
        candidate = (DEMO_ROOT / Path(*relative_path.parts)).resolve()
        if not candidate.is_relative_to(DEMO_ROOT.resolve()) or not candidate.is_file():
            raise ValueError("start_page must name a file inside the local demo site.")


@dataclass(frozen=True)
class ProposedAction:
    name: AgentActionName
    target: str
    value: str | None = None
    role: str | None = None
    reasoning: str = ""


@dataclass(frozen=True)
class TaskStep:
    number: int
    action: AgentActionName
    target: str
    url_before: str
    url_after: str
    result: str
    duration_ms: float
    reasoning: str = ""
    role: str | None = None


@dataclass(frozen=True)
class TaskResult:
    status: TaskStatus
    query: str
    records: tuple[AcquiredRecord, ...]
    steps: tuple[TaskStep, ...]
    pages_visited: tuple[str, ...]
    reason: str
    run_id: str | None = None


@dataclass
class AgentState:
    request: TaskRequest
    run_id: str | None = None
    steps: list[TaskStep] = field(default_factory=list)
    pages_visited: list[str] = field(default_factory=list)
    extracted_pages: set[str] = field(default_factory=set)
    records_by_id: dict[str, AcquiredRecord] = field(default_factory=dict)
    query_filled: bool = False
    search_submitted: bool = False

    def result(self, status: TaskStatus, reason: str) -> TaskResult:
        return TaskResult(
            status=status,
            query=self.request.query,
            records=tuple(self.records_by_id.values()),
            steps=tuple(self.steps),
            pages_visited=tuple(self.pages_visited),
            reason=reason,
            run_id=self.run_id,
        )
