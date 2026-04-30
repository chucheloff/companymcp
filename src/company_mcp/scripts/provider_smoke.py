import asyncio

import httpx

from company_mcp.config import settings
from company_mcp.mcp.schemas import RecentNewsInput
from company_mcp.providers.tavily_news import fetch_recent_news


async def _check_openrouter() -> tuple[bool, str]:
    if not settings.openrouter_enabled:
        return True, "OpenRouter skipped because OPENROUTER_ENABLED=false."
    if not settings.openrouter_api_key:
        return False, "OPENROUTER_API_KEY is missing."

    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return False, f"OpenRouter request failed: {exc}"

    data = payload.get("data", [])
    return True, f"OpenRouter reachable, models listed: {len(data)}"


async def _check_tavily() -> tuple[bool, str]:
    if not settings.tavily_api_key:
        return False, "TAVILY_API_KEY is missing."

    result = await fetch_recent_news(
        RecentNewsInput(
            company="Microsoft",
            domain="microsoft.com",
            days=7,
            limit=3,
            use_openrouter=False,
        )
    )
    if result.warnings and not result.items:
        return False, f"Tavily warning: {'; '.join(result.warnings)}"
    return True, f"Tavily reachable, items returned: {len(result.items)}"


async def main() -> None:
    tavily_ok, tavily_msg = await _check_tavily()
    openrouter_ok, openrouter_msg = await _check_openrouter()

    print(f"[Tavily] {'OK' if tavily_ok else 'FAIL'} - {tavily_msg}")
    print(f"[OpenRouter] {'OK' if openrouter_ok else 'FAIL'} - {openrouter_msg}")

    if not (tavily_ok and openrouter_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
