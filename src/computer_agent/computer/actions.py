from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import url2pathname

from playwright.async_api import Page

from computer_agent.computer.observations import PageObservation, observe_page


ActionName = Literal[
    "navigate",
    "fill",
    "click",
    "extract",
    "observe",
    "screenshot",
]

DEMO_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "fixture_site"
_DEMO_PAGE = DEMO_ROOT / "index.html"


class UnsafeNavigationError(ValueError):
    pass


@dataclass(frozen=True)
class AcquiredRecord:
    record_id: str
    title: str
    description: str
    source_url: str


@dataclass(frozen=True)
class ActionRecord:
    action: ActionName
    target: str
    url: str
    duration_ms: float


class BrowserActions:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._trace: list[ActionRecord] = []

    @property
    def trace(self) -> tuple[ActionRecord, ...]:
        return tuple(self._trace)

    async def open_demo_site(self, start_page: str = "index.html") -> None:
        started_at = perf_counter()
        page_path = (DEMO_ROOT / start_page).resolve()
        if not page_path.is_relative_to(DEMO_ROOT.resolve()) or not page_path.is_file():
            raise UnsafeNavigationError("Start page must be a local demo-site file.")
        await self._page.goto(page_path.as_uri())
        self._record("navigate", "demo-site", started_at)

    async def open_demo_url(self, url: str) -> None:
        started_at = perf_counter()
        _ensure_demo_destination(url)
        parsed_url = urlsplit(url)
        path = Path(url2pathname(unquote(parsed_url.path))).resolve()
        if not path.is_file():
            raise UnsafeNavigationError("Resume URL must name a local demo-site file.")
        await self._page.goto(url)
        self._record("navigate", "resume-checkpoint", started_at)

    async def fill_textbox(
        self,
        label: str,
        value: str,
        role: Literal["textbox", "searchbox"] = "textbox",
    ) -> None:
        started_at = perf_counter()
        textbox = self._page.get_by_role(role, name=label)
        await textbox.fill(value)
        if await textbox.input_value() != value:
            raise RuntimeError(f"Filling textbox {label!r} did not take effect.")
        self._record("fill", label, started_at)

    async def click_button(self, name: str) -> None:
        started_at = perf_counter()
        await self._page.get_by_role("button", name=name, exact=True).click()
        _ensure_demo_destination(self._page.url)
        self._record("click", name, started_at)

    async def click_link(self, name: str) -> str:
        started_at = perf_counter()
        link = self._page.get_by_role("link", name=name, exact=True)
        if await link.count() != 1:
            raise ValueError(f"Expected exactly one link named {name!r}.")

        href = await link.get_attribute("href")
        if not href:
            raise UnsafeNavigationError("The selected link has no destination.")

        destination = urljoin(self._page.url, href)
        _ensure_demo_destination(destination)
        await link.click()
        _ensure_demo_destination(self._page.url)
        self._record("click", name, started_at)
        return self._page.url

    async def extract_records(self) -> tuple[AcquiredRecord, ...]:
        started_at = perf_counter()
        raw_records = await self._page.locator("[data-record]").evaluate_all(
            """elements => elements.map(element => ({
                record_id: element.getAttribute("data-record"),
                title: element.querySelector("[data-title]")?.innerText.trim() ?? "",
                description: element.querySelector("[data-description]")
                    ?.innerText.trim() ?? "",
            }))"""
        )
        records: list[AcquiredRecord] = []
        for record in raw_records:
            if not record["record_id"] or not record["title"]:
                raise ValueError("A result record is missing its ID or title.")
            records.append(
                AcquiredRecord(
                    record_id=record["record_id"],
                    title=record["title"],
                    description=record["description"],
                    source_url=self._page.url,
                )
            )
        self._record("extract", f"{len(records)} records", started_at)
        return tuple(records)

    async def observe(self) -> PageObservation:
        started_at = perf_counter()
        observation = await observe_page(self._page)
        self._record("observe", "page", started_at)
        return observation

    async def screenshot(self) -> bytes:
        started_at = perf_counter()
        image = await self._page.screenshot()
        self._record("screenshot", "page", started_at)
        return image

    def _record(
        self,
        action: ActionName,
        target: str,
        started_at: float,
    ) -> None:
        duration_ms = (perf_counter() - started_at) * 1000
        self._trace.append(
            ActionRecord(
                action=action,
                target=target,
                url=self._page.url,
                duration_ms=duration_ms,
            )
        )


def _ensure_demo_destination(url: str) -> None:
    parsed_url = urlsplit(url)
    if parsed_url.scheme != "file" or parsed_url.netloc:
        raise UnsafeNavigationError("Only local demo-site links are permitted.")

    destination_path = Path(
        url2pathname(unquote(parsed_url.path))
    ).resolve()
    if not destination_path.is_relative_to(DEMO_ROOT.resolve()):
        raise UnsafeNavigationError(
            "The link destination is outside the local demo site."
        )
