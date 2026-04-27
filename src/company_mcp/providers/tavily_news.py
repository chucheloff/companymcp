import httpx
from urllib.parse import urlparse

from company_mcp.cache.store import get_json, set_json
from company_mcp.config import settings
from company_mcp.mcp.schemas import RecentNewsInput, RecentNewsItem, RecentNewsOutput

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def fetch_recent_news(data: RecentNewsInput) -> RecentNewsOutput:
    query = f"{data.company} company news"
    if data.domain:
        query = f"{query} {data.domain}"
    cache_key = f"recent_news:v1:{query}:{data.days}:{data.limit}"

    cached = await get_json(cache_key)
    if cached:
        return RecentNewsOutput.model_validate(cached)

    if not settings.tavily_api_key:
        return RecentNewsOutput(
            items=[],
            query_used=query,
            confidence=0.0,
            warnings=["TAVILY_API_KEY is not configured."],
        )

    warnings: list[str] = []
    items: list[RecentNewsItem] = []
    try:
        result_json = await tavily_search(
            query=query,
            topic="news",
            days=data.days,
            limit=data.limit,
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip().replace("\n", " ")
        if len(detail) > 220:
            detail = f"{detail[:220]}..."
        return RecentNewsOutput(
            items=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Tavily HTTP {exc.response.status_code}: {detail or 'No response body'}"],
        )
    except Exception as exc:
        return RecentNewsOutput(
            items=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Failed to fetch news from Tavily: {exc}"],
        )

    seen: set[str] = set()
    for row in result_json.get("results", []):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        seen.add(url)
        items.append(
            RecentNewsItem(
                title=title,
                url=url,
                published_at=row.get("published_date"),
                source=row.get("source") or _source_from_url(url),
                summary=row.get("content"),
                relevance=float(row.get("score") or 0.7),
            )
        )
        if len(items) >= data.limit:
            break

    if not items:
        warnings.append("No strong results returned by Tavily.")

    output = RecentNewsOutput(
        items=items,
        query_used=query,
        confidence=0.25 if not items else 0.7,
        warnings=warnings,
    )
    ttl_seconds = 3600 if data.days <= 7 else 6 * 3600
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    return output


async def tavily_search(
    *,
    query: str,
    topic: str = "general",
    days: int | None = None,
    limit: int = 8,
) -> dict:
    payload = {
        "query": query,
        "topic": topic,
        "max_results": limit,
        "include_answer": False,
        "include_raw_content": False,
    }
    if days is not None:
        payload["days"] = days
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            TAVILY_SEARCH_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "x-api-key": settings.tavily_api_key,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        return response.json()


def _source_from_url(url: str) -> str | None:
    hostname = urlparse(url).hostname
    return hostname.removeprefix("www.") if hostname else None
