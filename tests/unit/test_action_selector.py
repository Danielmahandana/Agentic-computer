from computer_agent.agent.action_selector import select_action
from computer_agent.agent.task_state import AgentState, TaskRequest
from computer_agent.computer.actions import DEMO_ROOT
from computer_agent.computer.observations import (
    InteractiveElement,
    PageObservation,
)


def test_selector_stops_before_following_a_visited_page() -> None:
    next_page_url = (DEMO_ROOT / "results-2.html").as_uri()
    state = AgentState(request=TaskRequest(query="electrician"))
    state.extracted_pages.add((DEMO_ROOT / "results-1.html").as_uri())
    state.pages_visited.append(next_page_url)
    observation = PageObservation(
        title="Search Results - Page 1",
        url=(DEMO_ROOT / "results-1.html").as_uri(),
        status_text=None,
        page_text="Page 1 of 2",
        record_count=1,
        textbox_count=0,
        button_count=0,
        interactive_elements=(
            InteractiveElement(
                role="link",
                accessible_name="Next page",
                tag="a",
                input_type=None,
                disabled=False,
                href=next_page_url,
            ),
        ),
    )

    action = select_action(state, observation)

    assert action is not None
    assert action.target == "loop detected"
