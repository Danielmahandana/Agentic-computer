import asyncio

import pytest
from fastapi.testclient import TestClient

import computer_agent.api.main as api_main
import computer_agent.config as config
import computer_agent.integrations.web_search as web_search
from computer_agent.api.main import create_app
from computer_agent.integrations.web_search import WebSearchError, search_web


class FakeResponse:
    is_error = False
    status_code = 200

    def json(self) -> dict[str, object]:
        return {
            "answer": "A concise sourced answer.",
            "results": [
                {
                    "title": f"Source {index}",
                    "url": f"https://www.example{index}.org/article",
                    "content": "A useful source excerpt.",
                    "score": 0.9,
                }
                for index in range(7)
            ],
        }


class FakeClient:
    last_request: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        self.options = kwargs

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, object],
    ) -> FakeResponse:
        type(self).last_request = {"url": url, "headers": headers, "json": json}
        return FakeResponse()


def test_keyless_search_returns_bounded_cited_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(web_search.httpx, "AsyncClient", FakeClient)

    response = asyncio.run(search_web("  local forest conservation  "))

    assert response.query == "local forest conservation"
    assert response.answer == "A concise sourced answer."
    assert len(response.results) == 5
    assert response.results[0].domain == "example0.org"
    request = FakeClient.last_request
    assert request["headers"]["X-Tavily-Access-Mode"] == "keyless"
    assert request["json"]["query"] == "local forest conservation"
    assert request["json"]["include_answer"] == "basic"


def test_search_reads_optional_tavily_key_from_project_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(web_search.httpx, "AsyncClient", FakeClient)
    (tmp_path / ".env").write_text(
        "TAVILY_API_KEY=placeholder-test-key\n",
        encoding="utf-8",
    )

    asyncio.run(search_web("web accessibility"))

    headers = FakeClient.last_request["headers"]
    assert headers["Authorization"] == "Bearer placeholder-test-key"
    assert "X-Tavily-Access-Mode" not in headers


def test_search_rejects_non_web_source_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)

    class UnsafeResponse(FakeResponse):
        def json(self) -> dict[str, object]:
            return {
                "answer": "",
                "results": [
                    {
                        "title": "Unsafe source",
                        "url": "javascript:alert(1)",
                        "content": "Not a web citation.",
                        "score": 0.1,
                    }
                ],
            }

    class UnsafeClient(FakeClient):
        async def post(
            self,
            url: str,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> UnsafeResponse:
            return UnsafeResponse()

    monkeypatch.setattr(web_search.httpx, "AsyncClient", UnsafeClient)
    with pytest.raises(WebSearchError, match="unsafe source URL"):
        asyncio.run(search_web("example query"))


def test_research_api_returns_search_results(monkeypatch, tmp_path) -> None:
    async def fake_search(query: str):
        return web_search.WebSearchResponse(
            query=query,
            answer="A sourced answer.",
            results=[
                web_search.WebSearchResult(
                    title="Source",
                    url="https://example.org/source",
                    snippet="A short excerpt.",
                    score=0.8,
                    domain="example.org",
                )
            ],
        )

    monkeypatch.setattr(api_main, "search_web", fake_search)
    with TestClient(create_app(tmp_path / "memory.sqlite3")) as client:
        response = client.post("/research", json={"query": "tree rings"})

    assert response.status_code == 200
    assert response.json()["answer"] == "A sourced answer."
    assert response.json()["results"][0]["url"] == "https://example.org/source"
