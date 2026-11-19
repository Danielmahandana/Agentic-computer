import asyncio

from computer_agent.agent.runtime import run_task
from computer_agent.agent.task_state import TaskRequest


def test_agent_searches_and_extracts_across_pages() -> None:
    result = asyncio.run(run_task(TaskRequest(query="electrician")))

    assert result.status == "completed"
    assert [record.record_id for record in result.records] == ["job-001", "job-003"]
    assert len(result.pages_visited) == 3
    assert [step.action for step in result.steps] == [
        "fill",
        "click",
        "extract",
        "click",
        "extract",
    ]
    assert result.steps[0].url_before == result.steps[0].url_after
    assert result.steps[1].url_before != result.steps[1].url_after
    assert all(step.duration_ms >= 0 for step in result.steps)


def test_agent_stops_at_configured_action_limit() -> None:
    result = asyncio.run(
        run_task(TaskRequest(query="electrician", max_steps=2))
    )

    assert result.status == "step_limit_reached"
    assert len(result.steps) == 2
    assert result.records == ()
    assert "maximum number" in result.reason
