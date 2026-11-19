from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from playwright.async_api import async_playwright

from computer_agent.computer.actions import BrowserActions


@asynccontextmanager
async def open_demo_computer(
    start_page: str = "index.html",
    start_url: str | None = None,
) -> AsyncIterator[BrowserActions]:
    async with AsyncExitStack() as cleanup:
        playwright = await async_playwright().start()
        cleanup.push_async_callback(playwright.stop)

        browser = await playwright.chromium.launch(
            headless=True,
            timeout=10_000,
        )
        cleanup.push_async_callback(browser.close)

        context = await browser.new_context()
        cleanup.push_async_callback(context.close)

        page = await context.new_page()
        page.set_default_timeout(5_000)
        page.set_default_navigation_timeout(10_000)

        computer = BrowserActions(page)
        if start_url is None:
            await computer.open_demo_site(start_page)
        else:
            await computer.open_demo_url(start_url)

        yield computer
