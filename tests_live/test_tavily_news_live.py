import os

import pytest

from company_mcp.config import settings
from company_mcp.mcp.schemas import RecentNewsInput
from company_mcp.providers.tavily_news import fetch_recent_news


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_live_tavily_recent_news_search_returns_normalized_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not settings.tavily_api_key:
        pytest.skip("TAVILY_API_KEY is not configured.")

    async def fake_get_json(_key: str):
        return None

    async def fake_set_json(_key: str, _value: dict, ttl_seconds: int):
        _ = ttl_seconds
        return True

    monkeypatch.setattr("company_mcp.providers.tavily_news.get_json", fake_get_json)
    monkeypatch.setattr("company_mcp.providers.tavily_news.set_json", fake_set_json)

    company = os.getenv("LIVE_TAVILY_COMPANY", "OpenAI")
    domain = os.getenv("LIVE_TAVILY_DOMAIN", "openai.com")

    result = await fetch_recent_news(
        RecentNewsInput(
            company=company,
            domain=domain,
            days=14,
            limit=5,
        )
    )

    assert result.query_used == f"{company} company news {domain}"
    assert result.confidence >= 0.7
    assert not result.warnings
    assert result.items

    for item in result.items:
        assert item.title
        assert item.url.startswith("https://")
        assert item.source
        assert item.relevance > 0
