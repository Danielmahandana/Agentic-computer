import os
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from computer_agent.config import read_project_env


_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_MAX_RESULTS = 5
_MAX_SNIPPET_LENGTH = 1_200
_MAX_ANSWER_LENGTH = 6_000


class WebSearchError(RuntimeError):
    pass


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)

    def normalized_query(self) -> str:
        query = self.query.strip()
        if not query:
            raise ValueError("Please enter a search query.")
        return query


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    score: float
    domain: str


class WebSearchResponse(BaseModel):
    query: str
    answer: str
    results: list[WebSearchResult]
    source: str = "Tavily"


async def search_web(query: str) -> WebSearchResponse:
    normalized_query = WebSearchRequest(query=query).normalized_query()
    values = read_project_env({"TAVILY_API_KEY"})
    api_key = os.getenv("TAVILY_API_KEY") or values.get("TAVILY_API_KEY")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["X-Tavily-Access-Mode"] = "keyless"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
        ) as client:
            response = await client.post(
                _TAVILY_SEARCH_URL,
                headers=headers,
                json={
                    "query": normalized_query,
                    "topic": "general",
                    "search_depth": "basic",
                    "max_results": _MAX_RESULTS,
                    "include_answer": "basic",
                },
            )
    except httpx.TimeoutException as error:
        raise WebSearchError("The web search took too long. Please try again.") from error
    except httpx.RequestError as error:
        raise WebSearchError(
            "I couldn't connect to the web search provider. Please try again."
        ) from error

    if response.is_error:
        if response.status_code == 429:
            raise WebSearchError(
                "The web search provider's rate limit was reached. Please try again later."
            )
        raise WebSearchError(
            f"The web search provider returned HTTP {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise WebSearchError(
            "The web search provider returned an unreadable response."
        ) from error
    return _parse_response(normalized_query, payload)


def _parse_response(query: str, payload: object) -> WebSearchResponse:
    if not isinstance(payload, dict):
        raise WebSearchError("The web search provider returned an invalid response.")

    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise WebSearchError("The web search provider returned no result list.")

    results: list[WebSearchResult] = []
    for raw_result in raw_results[:_MAX_RESULTS]:
        if not isinstance(raw_result, dict):
            raise WebSearchError("The web search provider returned an invalid result.")
        title = raw_result.get("title")
        url = raw_result.get("url")
        content = raw_result.get("content")
        score = raw_result.get("score")
        if (
            not isinstance(title, str)
            or not isinstance(url, str)
            or not isinstance(content, str)
            or not isinstance(score, (int, float))
        ):
            raise WebSearchError("The web search provider returned an incomplete result.")

        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise WebSearchError("The web search provider returned an unsafe source URL.")
        results.append(
            WebSearchResult(
                title=title[:300],
                url=url,
                snippet=content[:_MAX_SNIPPET_LENGTH],
                score=float(score),
                domain=parsed_url.hostname.removeprefix("www."),
            )
        )

    answer = payload.get("answer", "")
    if not isinstance(answer, str):
        raise WebSearchError("The web search provider returned an invalid answer.")
    return WebSearchResponse(
        query=query,
        answer=answer[:_MAX_ANSWER_LENGTH],
        results=results,
    )
