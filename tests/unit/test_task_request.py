import pytest

from computer_agent.agent.task_state import TaskRequest


@pytest.mark.parametrize(
    ("query", "max_steps", "timeout_seconds", "start_page"),
    [
        (" ", 12, 30.0, "index.html"),
        ("electrician", 0, 30.0, "index.html"),
        ("electrician", 21, 30.0, "index.html"),
        ("electrician", 12, 0.0, "index.html"),
        ("electrician", 12, 60.1, "index.html"),
        ("electrician", 12, 30.0, "../outside.html"),
    ],
)
def test_task_request_rejects_invalid_limits(
    query: str,
    max_steps: int,
    timeout_seconds: float,
    start_page: str,
) -> None:
    with pytest.raises(ValueError):
        TaskRequest(
            query=query,
            max_steps=max_steps,
            timeout_seconds=timeout_seconds,
            start_page=start_page,
        )
