import re
from dataclasses import dataclass
from typing import Protocol

from computer_agent.agent.task_state import (
    AgentState,
    ProposedAction,
)
from computer_agent.computer.actions import _ensure_demo_destination
from computer_agent.computer.observations import (
    InteractiveElement,
    PageObservation,
)


_SEARCH_ACTION_NAME = re.compile(r"\b(search|find|submit)\b", re.IGNORECASE)
_NEXT_PAGE_NAME = re.compile(
    r"\b(next|more|older|continue|page\s*\d+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PlanningContext:
    state: AgentState
    observation: PageObservation


class Planner(Protocol):
    async def propose_action(self, context: PlanningContext) -> ProposedAction:
        ...


class HeuristicPlanner:
    async def propose_action(self, context: PlanningContext) -> ProposedAction:
        state = context.state
        observation = context.observation

        if not state.query_filled:
            textboxes = [
                element
                for element in observation.interactive_elements
                if element.role in {"textbox", "searchbox"} and not element.disabled
            ]
            preferred = [
                element
                for element in textboxes
                if element.accessible_name
                and re.search(r"search|query|term|phrase", element.accessible_name, re.I)
            ]
            candidates = preferred or textboxes
            if len(candidates) != 1:
                raise RuntimeError(
                    "Heuristics could not identify one unambiguous search field."
                )
            return ProposedAction(
                name="fill",
                target=candidates[0].accessible_name or "",
                value=state.request.query,
                role=candidates[0].role,
                reasoning="Selected the only suitable search field.",
            )

        if not state.search_submitted:
            buttons = [
                element
                for element in observation.interactive_elements
                if element.role == "button"
                and not element.disabled
                and element.accessible_name
                and _SEARCH_ACTION_NAME.search(element.accessible_name)
            ]
            if len(buttons) != 1:
                raise RuntimeError(
                    "Heuristics could not identify one unambiguous search button."
                )
            return ProposedAction(
                name="click",
                target=buttons[0].accessible_name or "",
                role="button",
                reasoning="Selected the uniquely named search action.",
            )

        if observation.record_count and observation.url not in state.extracted_pages:
            return ProposedAction(
                name="extract",
                target="records",
                reasoning="The page contains records that have not been extracted.",
            )

        next_links = [
            element
            for element in observation.interactive_elements
            if element.role == "link"
            and not element.disabled
            and element.accessible_name
            and _NEXT_PAGE_NAME.search(element.accessible_name)
        ]
        if next_links:
            if len(next_links) != 1:
                raise RuntimeError(
                    "Heuristics found multiple possible pagination links."
                )
            next_link = next_links[0]
            if next_link.href is None:
                raise RuntimeError("The pagination link has no destination.")
            if next_link.href in state.pages_visited:
                return ProposedAction(
                    name="click",
                    target="loop detected",
                    role="link",
                )
            return ProposedAction(
                name="click",
                target=next_link.accessible_name or "",
                role="link",
                reasoning="Followed the visible pagination link.",
            )

        return ProposedAction(
            name="finish",
            target="task complete",
            reasoning="No unvisited results or pagination controls remain.",
        )


def validate_proposal(
    context: PlanningContext,
    proposal: ProposedAction,
) -> ProposedAction:
    state = context.state
    observation = context.observation

    if proposal.name == "fill":
        if state.query_filled or state.search_submitted:
            raise ValueError("The planner may fill the task query only once.")
        _require_control(observation, proposal, {"textbox", "searchbox"})
        return ProposedAction(
            name="fill",
            target=proposal.target,
            value=state.request.query,
            role=proposal.role,
            reasoning=proposal.reasoning[:300],
        )

    if proposal.name == "click":
        if proposal.target == "loop detected":
            raise ValueError("The planner cannot request a known pagination loop.")
        control = _require_control(
            observation,
            proposal,
            {"button", "link"},
        )
        if control.role == "link":
            if control.href is None:
                raise ValueError("The selected link has no destination.")
            _ensure_demo_destination(control.href)
        return ProposedAction(
            name="click",
            target=proposal.target,
            role=control.role,
            reasoning=proposal.reasoning[:300],
        )

    if proposal.name == "extract":
        if observation.url in state.extracted_pages:
            raise ValueError("This page has already been extracted.")
        if not observation.record_count:
            raise ValueError("The page has no extractable records.")
        return ProposedAction(
            name="extract",
            target="records",
            reasoning=proposal.reasoning[:300],
        )

    if proposal.name == "finish":
        if not state.search_submitted or len(state.pages_visited) < 2:
            raise ValueError("The planner cannot finish before opening results.")
        if observation.record_count and observation.url not in state.extracted_pages:
            raise ValueError("The current page still has unextracted records.")
        for element in observation.interactive_elements:
            if (
                element.role in {"link", "button"}
                and element.accessible_name
                and _NEXT_PAGE_NAME.search(element.accessible_name)
                and not element.disabled
            ):
                if element.role == "button" or element.href not in state.pages_visited:
                    raise ValueError("A possible pagination control remains.")
        return ProposedAction(
            name="finish",
            target="task complete",
            reasoning=proposal.reasoning[:300],
        )

    raise ValueError(f"Unsupported proposed action: {proposal.name!r}.")


def _require_control(
    observation: PageObservation,
    proposal: ProposedAction,
    allowed_roles: set[str],
) -> InteractiveElement:
    if proposal.role not in allowed_roles or not proposal.target:
        raise ValueError("The proposed action has an invalid role or target.")
    matches = [
        element
        for element in observation.interactive_elements
        if element.role == proposal.role
        and element.accessible_name == proposal.target
        and not element.disabled
    ]
    if len(matches) != 1:
        raise ValueError(
            "The proposed target must uniquely match a visible, enabled control."
        )
    return matches[0]
