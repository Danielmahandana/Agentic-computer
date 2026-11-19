import asyncio
import json
from types import SimpleNamespace

import pytest

from computer_agent.agent.planner import PlanningContext, validate_proposal
from computer_agent.agent.task_state import AgentState, ProposedAction, TaskRequest
from computer_agent.computer.actions import DEMO_ROOT
from computer_agent.computer.observations import (
    InteractiveElement,
    PageObservation,
)
from computer_agent.intelligence.model_provider import (
    GroqProvider,
    OllamaProvider,
    _parse_proposal,
)
import computer_agent.config as config
import computer_agent.intelligence.model_provider as model_provider


def _observation(
    controls: tuple[InteractiveElement, ...] = (),
    url: str | None = None,
    record_count: int = 0,
) -> PageObservation:
    return PageObservation(
        title="Local page",
        url=url or (DEMO_ROOT / "library" / "portal.html").as_uri(),
        status_text=None,
        page_text="Local test content",
        record_count=record_count,
        textbox_count=0,
        button_count=0,
        interactive_elements=controls,
    )


def test_model_proposal_cannot_target_an_unobserved_control() -> None:
    state = AgentState(request=TaskRequest(query="electrician"))
    context = PlanningContext(state, _observation())
    proposal = ProposedAction(
        name="click",
        target="Delete everything",
        role="button",
    )

    with pytest.raises(ValueError, match="visible, enabled control"):
        validate_proposal(context, proposal)


def test_model_cannot_finish_before_search_results_are_opened() -> None:
    state = AgentState(request=TaskRequest(query="electrician"))
    context = PlanningContext(state, _observation())

    with pytest.raises(ValueError, match="before opening results"):
        validate_proposal(
            context,
            ProposedAction(name="finish", target="task complete"),
        )


def test_model_cannot_finish_while_a_next_page_control_is_available() -> None:
    state = AgentState(request=TaskRequest(query="electrician"))
    state.query_filled = True
    state.search_submitted = True
    state.pages_visited.extend(
        [
            (DEMO_ROOT / "library" / "portal.html").as_uri(),
            (DEMO_ROOT / "library" / "hits.html").as_uri(),
        ]
    )
    state.extracted_pages.add((DEMO_ROOT / "library" / "hits.html").as_uri())
    next_page = InteractiveElement(
        role="link",
        accessible_name="Next page",
        tag="a",
        input_type=None,
        disabled=False,
        href=(DEMO_ROOT / "library" / "more.html").as_uri(),
    )
    context = PlanningContext(
        state,
        _observation(
            (next_page,),
            url=(DEMO_ROOT / "library" / "hits.html").as_uri(),
        ),
    )

    with pytest.raises(ValueError, match="pagination control"):
        validate_proposal(
            context,
            ProposedAction(name="finish", target="task complete"),
        )


def test_model_cannot_propose_external_link_navigation() -> None:
    control = InteractiveElement(
        role="link",
        accessible_name="Open external site",
        tag="a",
        input_type=None,
        disabled=False,
        href="https://example.com/",
    )
    context = PlanningContext(
        AgentState(request=TaskRequest(query="electrician")),
        _observation((control,)),
    )

    with pytest.raises(ValueError, match="local demo-site"):
        validate_proposal(
            context,
            ProposedAction(
                name="click",
                target="Open external site",
                role="link",
            ),
        )


def test_ollama_provider_rejects_non_loopback_endpoints() -> None:
    with pytest.raises(ValueError, match="local loopback"):
        OllamaProvider(
            "qwen2.5-coder:3b",
            endpoint="http://example.com:11434/api/chat",
        )


def test_groq_provider_reads_legacy_key_label_without_logging_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "groq key = placeholder-not-a-real-key\n",
        encoding="utf-8",
    )
    provider = GroqProvider()

    async def fake_request(messages: list[dict[str, str]]) -> str:
        assert messages[0]["role"] == "system"
        assert "electrician" in messages[1]["content"]
        return json.dumps(
            {
                "action": "fill",
                "target": "Search jobs",
                "role": "textbox",
                "reason": "Use the visible search field.",
            }
        )

    monkeypatch.setattr(provider, "_request", fake_request)
    proposal = asyncio.run(
        provider.propose_action(
            PlanningContext(
                AgentState(request=TaskRequest(query="electrician")),
                _observation(),
            )
        )
    )

    assert proposal.name == "fill"
    assert proposal.target == "Search jobs"
    assert provider._model == "llama-3.3-70b-versatile"
    assert "placeholder-not-a-real-key" not in caplog.text


def test_groq_provider_requires_a_key_when_env_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqProvider()


def test_groq_provider_uses_json_mode_without_a_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_options: dict[str, object] = {}
    request_options: dict[str, object] = {}
    response_text = (
        '{"action":"extract","target":"records","role":null,"reason":"Collect records."}'
    )

    class FakeCompletions:
        async def create(self, **kwargs: object) -> object:
            request_options.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=response_text)
                    )
                ]
            )

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)
            self.chat = SimpleNamespace(
                completions=FakeCompletions(),
            )

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(model_provider, "AsyncGroq", FakeClient)
    provider = GroqProvider(model="test-model", api_key="test-key")

    result = asyncio.run(provider._request([{"role": "user", "content": "test"}]))

    assert result == response_text
    assert client_options["api_key"] == "test-key"
    assert request_options["model"] == "test-model"
    assert request_options["response_format"] == {"type": "json_object"}


def test_model_response_rejects_unrestricted_actions() -> None:
    with pytest.raises(ValueError, match="unsupported action"):
        _parse_proposal(
            '{"action":"execute_python","target":"code","role":null,"reason":"test"}'
        )
