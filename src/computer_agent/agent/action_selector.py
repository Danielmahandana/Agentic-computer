from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

from computer_agent.agent.task_state import (
    AgentActionName,
    AgentState,
    ProposedAction,
)
from computer_agent.computer.actions import DEMO_ROOT
from computer_agent.computer.observations import PageObservation


def select_action(
    state: AgentState,
    observation: PageObservation,
) -> ProposedAction | None:
    current_path = _local_page_path(observation.url)
    if current_path == (DEMO_ROOT / "index.html").resolve():
        if not state.query_filled:
            return _require_control(
                observation,
                "textbox",
                "Search query",
                "fill",
                state.request.query,
            )
        if not state.search_submitted:
            return _require_control(observation, "button", "Search", "click")
        raise RuntimeError("Search submission did not leave the search page.")

    if current_path not in {
        (DEMO_ROOT / "results-1.html").resolve(),
        (DEMO_ROOT / "results-2.html").resolve(),
    }:
        raise RuntimeError("The agent reached an unrecognized local demo page.")

    if observation.url not in state.extracted_pages:
        return ProposedAction(name="extract", target="search results")

    next_page = next(
        (
            element
            for element in observation.interactive_elements
            if element.role == "link"
            and element.accessible_name == "Next page"
            and not element.disabled
        ),
        None,
    )
    if next_page is None:
        return None
    if next_page.href is None:
        raise RuntimeError("The next-page link has no destination.")
    if next_page.href in state.pages_visited:
        return ProposedAction(name="click", target="loop detected")

    return ProposedAction(name="click", target="Next page", role="link")


def _require_control(
    observation: PageObservation,
    role: str,
    name: str,
    action: AgentActionName,
    value: str | None = None,
) -> ProposedAction:
    control = next(
        (
            element
            for element in observation.interactive_elements
            if element.role == role
            and element.accessible_name == name
            and not element.disabled
        ),
        None,
    )
    if control is None:
        raise RuntimeError(f"Required {role} {name!r} is not available.")
    return ProposedAction(name=action, target=name, value=value, role=role)


def _local_page_path(url: str) -> Path:
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "file" or parsed_url.netloc:
        raise RuntimeError("The agent is restricted to the local demo site.")
    path = Path(url2pathname(unquote(parsed_url.path))).resolve()
    if not path.is_relative_to(DEMO_ROOT.resolve()):
        raise RuntimeError("The agent left the local demo-site directory.")
    return path
