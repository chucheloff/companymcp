from collections.abc import Callable

from playwright.async_api import BrowserContext, Route, TimeoutError as PlaywrightTimeoutError, async_playwright

from company_mcp.config import settings
from company_mcp.extractors.base import PageDocument
from company_mcp.extractors.html_utils import extract_meta, extract_text, extract_title


async def snapshot_url(url: str, *, validate_url: Callable[[str], str] | None = None) -> PageDocument:
    result = (await snapshot_urls([url], validate_url=validate_url))[0]
    if isinstance(result, Exception):
        raise result
    return result


async def snapshot_urls(
    urls: list[str],
    *,
    validate_url: Callable[[str], str] | None = None,
) -> list[PageDocument | Exception]:
    if not urls:
        return []
    for url in urls:
        if validate_url:
            validate_url(url)

    results: list[PageDocument | Exception] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        try:
            for url in urls:
                try:
                    results.append(await _snapshot_with_context(context, url, validate_url=validate_url))
                except Exception as exc:
                    results.append(exc)
        finally:
            await browser.close()
    return results


async def _snapshot_with_context(
    context: BrowserContext,
    url: str,
    *,
    validate_url: Callable[[str], str] | None = None,
) -> PageDocument:
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

    page = await context.new_page()
    await page.route("**/*", guard_request)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms)
        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=min(settings.browser_timeout_ms, 2_000),
            )
        except PlaywrightTimeoutError:
            pass
        html = await page.content()
        final_url = page.url
        if validate_url:
            validate_url(final_url)
    finally:
        await page.close()

    return PageDocument(
        url=final_url,
        title=extract_title(html) or final_url,
        html=html,
        text=extract_text(html),
        metadata=extract_meta(html),
    )
