import asyncio

from computer_agent.agent.planner import HeuristicPlanner
from computer_agent.agent.runtime import run_task
from computer_agent.agent.task_state import TaskRequest


def test_heuristic_planner_handles_an_unfamiliar_local_site() -> None:
    result = asyncio.run(
        run_task(
            TaskRequest(
                query="electrician",
                start_page="library/portal.html",
            ),
            planner=HeuristicPlanner(),
        )
    )

    assert result.status == "completed"
    assert [record.record_id for record in result.records] == ["report-101"]
    assert [step.action for step in result.steps] == [
        "fill",
        "click",
        "extract",
        "finish",
    ]
    assert result.steps[0].reasoning
    assert all("library" in url for url in result.pages_visited)
