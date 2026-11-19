from computer_agent.agent.task_state import AgentState, ProposedAction
from computer_agent.computer.actions import AcquiredRecord
from computer_agent.computer.observations import PageObservation


def verify_action(
    state: AgentState,
    action: ProposedAction,
    url_before: str,
    observation: PageObservation,
    extracted_records: tuple[AcquiredRecord, ...] = (),
) -> str:
    if action.name == "fill":
        if observation.url != url_before:
            raise RuntimeError("Filling the search field unexpectedly navigated.")
        if action.value is None:
            raise RuntimeError("The fill action has no search query.")
        state.query_filled = True
        return "Search field filled."

    if action.name == "click":
        if observation.url == url_before:
            raise RuntimeError("The click did not navigate to a new page.")
        if observation.url in state.pages_visited:
            raise RuntimeError("The click led to a previously visited page.")
        state.pages_visited.append(observation.url)
        if not state.search_submitted:
            if not state.query_filled:
                raise RuntimeError("Navigation occurred before the task query was filled.")
            state.search_submitted = True
            return "Search results opened."
        return "Opened the next page."

    if action.name == "extract":
        if observation.url != url_before:
            raise RuntimeError("Extracting records unexpectedly navigated.")
        matching_records = tuple(
            record
            for record in extracted_records
            if state.request.query.casefold()
            in f"{record.title} {record.description}".casefold()
        )
        for record in matching_records:
            existing = state.records_by_id.get(record.record_id)
            if existing is not None and (
                existing.title != record.title
                or existing.description != record.description
            ):
                raise RuntimeError(
                    f"Record ID {record.record_id!r} changed during this task."
                )
            state.records_by_id.setdefault(record.record_id, record)
        state.extracted_pages.add(observation.url)
        return f"Verified {len(matching_records)} matching records."

    raise RuntimeError(
        f"Cannot verify action {action.name!r} for target {action.target!r}."
    )


def verify_completion(
    state: AgentState,
    observation: PageObservation,
) -> str:
    if not state.search_submitted or len(state.pages_visited) < 2:
        raise RuntimeError("The task cannot complete before opening search results.")
    if observation.record_count and observation.url not in state.extracted_pages:
        raise RuntimeError("The current page still has unextracted records.")
    return "The current results were extracted and no further action was proposed."
