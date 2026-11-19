import asyncio
from dataclasses import asdict
from time import perf_counter
from uuid import uuid4

from computer_agent.agent.action_selector import select_action
from computer_agent.agent.control import TaskControl, TaskStopped
from computer_agent.agent.planner import (
    Planner,
    PlanningContext,
    validate_proposal,
)
from computer_agent.agent.task_state import (
    AgentState,
    ProposedAction,
    TaskRequest,
    TaskResult,
    TaskStatus,
    TaskStep,
)
from computer_agent.agent.verifier import verify_action, verify_completion
from computer_agent.computer.actions import AcquiredRecord, BrowserActions
from computer_agent.computer.observations import PageObservation
from computer_agent.computer.session import open_demo_computer
from computer_agent.memory.store import SQLiteMemory, VerifiedProcedure


async def run_task(
    request: TaskRequest,
    planner: Planner | None = None,
    memory: SQLiteMemory | None = None,
    run_id: str | None = None,
    control: TaskControl | None = None,
) -> TaskResult:
    if memory is not None and run_id is None:
        run_id = str(uuid4())
    state = AgentState(request=request, run_id=run_id)
    if memory is not None and run_id is not None:
        memory.create_run(run_id, request)
    return await _execute_task(state, planner, memory, control=control)


async def resume_task(
    run_id: str,
    memory: SQLiteMemory,
    planner: Planner | None = None,
    max_steps: int = 20,
    timeout_seconds: float = 30.0,
) -> TaskResult:
    snapshot = memory.load_run(run_id)
    if snapshot.status not in {"running", "step_limit_reached", "timed_out"}:
        raise ValueError(f"Task run {run_id!r} cannot resume from {snapshot.status!r}.")

    state = snapshot.state
    state.request = TaskRequest(
        query=snapshot.request.query,
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
        start_page=snapshot.request.start_page,
    )
    if not state.search_submitted:
        state.query_filled = False
    memory.set_running(run_id)
    return await _execute_task(
        state,
        planner,
        memory,
        start_url=snapshot.page_url,
    )


async def replay_procedure(
    procedure: VerifiedProcedure,
    request: TaskRequest,
    memory: SQLiteMemory | None = None,
    run_id: str | None = None,
    control: TaskControl | None = None,
) -> TaskResult:
    if request.start_page != procedure.start_page:
        raise ValueError("Procedure replay must use its verified start page.")

    if memory is not None and run_id is None:
        run_id = str(uuid4())
    state = AgentState(request=request, run_id=run_id)
    if memory is not None and run_id is not None:
        memory.create_run(run_id, request)

    page_url: str | None = None
    try:
        async with asyncio.timeout(request.timeout_seconds):
            async with open_demo_computer(request.start_page) as computer:
                observation = await computer.observe()
                page_url = observation.url
                state.pages_visited.append(observation.url)
                if memory is not None and run_id is not None:
                    memory.save_progress(run_id, state, observation.url)
                if control is not None:
                    control.publish("observation", asdict(observation))

                for saved_action in procedure.actions:
                    if control is not None:
                        await control.wait_until_resumed()
                    action = validate_proposal(
                        PlanningContext(state, observation),
                        saved_action,
                    )
                    if action.target == "loop detected":
                        return _finish(
                            state,
                            "loop_detected",
                            "The verified procedure encountered a pagination loop.",
                            memory,
                            observation.url,
                        )
                    if len(state.steps) >= request.max_steps:
                        return _finish(
                            state,
                            "step_limit_reached",
                            "The maximum number of actions was reached before completion.",
                            memory,
                            observation.url,
                        )

                    observation, step = await _perform_action(
                        computer,
                        state,
                        action,
                        observation,
                    )
                    page_url = observation.url
                    state.steps.append(step)
                    if memory is not None and run_id is not None:
                        memory.save_progress(run_id, state, observation.url)
                    if control is not None:
                        control.publish("step", asdict(step))
                        control.publish("observation", asdict(observation))

                reason = verify_completion(state, observation)
                finish_step = _finish_step(
                    len(state.steps) + 1,
                    action=None,
                    observation=observation,
                    reason=reason,
                )
                state.steps.append(finish_step)
                if control is not None:
                    control.publish("step", asdict(finish_step))
                return _finish(
                    state,
                    "completed",
                    reason,
                    memory,
                    observation.url,
                )
    except TaskStopped:
        return _finish(
            state,
            "terminated",
            "The procedure replay was terminated at a safe action boundary.",
            memory,
            page_url,
        )
    except TimeoutError:
        return _finish(
            state,
            "timed_out",
            "The procedure replay exceeded its configured time limit.",
            memory,
            page_url,
        )


async def _execute_task(
    state: AgentState,
    planner: Planner | None,
    memory: SQLiteMemory | None,
    start_url: str | None = None,
    control: TaskControl | None = None,
) -> TaskResult:
    request = state.request
    page_url: str | None = None
    try:
        async with asyncio.timeout(request.timeout_seconds):
            async with open_demo_computer(request.start_page, start_url) as computer:
                observation = await computer.observe()
                page_url = observation.url
                if start_url is None:
                    state.pages_visited.append(observation.url)
                elif observation.url != start_url:
                    raise RuntimeError("The browser did not restore the saved checkpoint.")
                if memory is not None and state.run_id is not None:
                    memory.save_progress(state.run_id, state, observation.url)
                if control is not None:
                    control.publish("observation", asdict(observation))

                while True:
                    if control is not None:
                        await control.wait_until_resumed()
                    if planner is None:
                        action = select_action(state, observation)
                        if action is None:
                            return _finish(
                                state,
                                "completed",
                                "Visited all result pages and verified the extracted records.",
                                memory,
                                observation.url,
                            )
                    else:
                        context = PlanningContext(state, observation)
                        action = validate_proposal(
                            context,
                            await planner.propose_action(context),
                        )
                    if control is not None:
                        await control.wait_until_resumed()

                    if action.target == "loop detected":
                        return _finish(
                            state,
                            "loop_detected",
                            "The next-page link points to a page already visited.",
                            memory,
                            observation.url,
                        )
                    if action.name == "finish":
                        reason = verify_completion(state, observation)
                        state.steps.append(
                            _finish_step(
                                len(state.steps) + 1,
                                action,
                                observation,
                                reason,
                            )
                        )
                        return _finish(
                            state,
                            "completed",
                            reason,
                            memory,
                            observation.url,
                        )
                    if len(state.steps) >= request.max_steps:
                        return _finish(
                            state,
                            "step_limit_reached",
                            "The maximum number of actions was reached before completion.",
                            memory,
                            observation.url,
                        )

                    observation, step = await _perform_action(
                        computer,
                        state,
                        action,
                        observation,
                    )
                    page_url = observation.url
                    state.steps.append(step)
                    if memory is not None and state.run_id is not None:
                        memory.save_progress(state.run_id, state, observation.url)
                    if control is not None:
                        control.publish("step", asdict(step))
                        control.publish("observation", asdict(observation))
    except TaskStopped:
        return _finish(
            state,
            "terminated",
            "Task terminated by user.",
            memory,
            page_url,
        )
    except TimeoutError:
        return _finish(
            state,
            "timed_out",
            "The task exceeded its configured time limit.",
            memory,
        )


async def _perform_action(
    computer: BrowserActions,
    state: AgentState,
    action: ProposedAction,
    observation: PageObservation,
) -> tuple[PageObservation, TaskStep]:
    url_before = observation.url
    started_at = perf_counter()
    extracted_records = await _execute(computer, action, state.request)
    observation = await computer.observe()
    result = verify_action(
        state,
        action,
        url_before,
        observation,
        extracted_records,
    )
    step = TaskStep(
        number=len(state.steps) + 1,
        action=action.name,
        target=action.target,
        url_before=url_before,
        url_after=observation.url,
        result=result,
        duration_ms=(perf_counter() - started_at) * 1000,
        reasoning=action.reasoning,
        role=action.role,
    )
    return observation, step


def _finish_step(
    number: int,
    action: ProposedAction | None,
    observation: PageObservation,
    reason: str,
) -> TaskStep:
    started_at = perf_counter()
    return TaskStep(
        number=number,
        action="finish",
        target="task complete" if action is None else action.target,
        url_before=observation.url,
        url_after=observation.url,
        result=reason,
        duration_ms=(perf_counter() - started_at) * 1000,
        reasoning="" if action is None else action.reasoning,
    )


def _finish(
    state: AgentState,
    status: TaskStatus,
    reason: str,
    memory: SQLiteMemory | None,
    page_url: str | None = None,
) -> TaskResult:
    result = state.result(status, reason)
    if memory is not None and state.run_id is not None:
        if page_url is not None:
            memory.finish_run(state.run_id, result, state, page_url)
        else:
            memory.finish_run(state.run_id, result)
    return result


async def _execute(
    computer: BrowserActions,
    action: ProposedAction,
    request: TaskRequest,
) -> tuple[AcquiredRecord, ...]:
    if action.name == "fill":
        if action.role not in {"textbox", "searchbox"}:
            raise RuntimeError("Fill action must target a textbox or searchbox.")
        await computer.fill_textbox(action.target, request.query, action.role)
        return ()
    if action.name == "click":
        if action.role == "button":
            await computer.click_button(action.target)
        elif action.role == "link":
            await computer.click_link(action.target)
        else:
            raise RuntimeError("Click action must target a button or link.")
        return ()
    if action.name == "extract":
        return await computer.extract_records()
    raise RuntimeError(
        f"Unsupported action {action.name!r} for target {action.target!r}."
    )
