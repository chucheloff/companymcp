from collections.abc import Callable

from playwright.async_api import Route, async_playwright

from company_mcp.config import settings
from company_mcp.extractors.base import PageDocument
from company_mcp.extractors.html_utils import extract_meta, extract_text, extract_title


async def snapshot_url(url: str, *, validate_url: Callable[[str], str] | None = None) -> PageDocument:
    if validate_url:
        validate_url(url)

    async def guard_request(route: Route) -> None:
        if validate_url:
            try:
                validate_url(route.request.url)
            except Exception:
                await route.abort()
                return
        await route.continue_()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", guard_request)
        try:
            await page.goto(url, wait_until="networkidle", timeout=settings.browser_timeout_ms)
            html = await page.content()
            final_url = page.url
            if validate_url:
                validate_url(final_url)
        finally:
            await browser.close()

    return PageDocument(
        url=final_url,
        title=extract_title(html) or final_url,
        html=html,
        text=extract_text(html),
        metadata=extract_meta(html),
    )
