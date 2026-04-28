import httpx
from urllib.parse import urlparse

from company_mcp.cache.company_table import upsert_company_provider_result
from company_mcp.cache.store import get_json, get_ttl, set_json
from company_mcp.config import settings
from company_mcp.mcp.schemas import RecentNewsInput, RecentNewsItem, RecentNewsOutput
from company_mcp.models.openrouter import OpenRouterClient, OpenRouterUnavailable

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def fetch_recent_news(data: RecentNewsInput) -> RecentNewsOutput:
    query = f"{data.company} company news"
    if data.domain:
        query = f"{query} {data.domain}"
    cache_key = f"recent_news:v2:{query}:{data.days}:{data.limit}"

    cached = None if data.force_refresh else await get_json(cache_key)
    if cached:
        output = RecentNewsOutput.model_validate(cached)
        ttl_seconds = await get_ttl(cache_key) or _ttl_seconds(data)
        await upsert_company_provider_result(
            company=data.company,
            provider="recent_news",
            result=output.model_dump(mode="json"),
            ttl_seconds=ttl_seconds,
            request=data.model_dump(mode="json"),
        )
        return output

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
    summarizer = OpenRouterClient() if settings.openrouter_api_key else None
    for row in result_json.get("results", []):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        if not url or not title or url in seen:
            continue
        seen.add(url)
        summary = row.get("content")
        if summarizer and summary:
            try:
                summary = await summarizer.summarize_text(
                    _news_summary_prompt(
                        title=title,
                        source=row.get("source") or _source_from_url(url),
                        published_at=row.get("published_date"),
                        content=summary,
                    )
                )
            except OpenRouterUnavailable as exc:
                warnings.append(str(exc))
                summarizer = None
            except Exception as exc:
                warnings.append(f"OpenRouter news summarization failed for {url}: {exc}")
        items.append(
            RecentNewsItem(
                title=title,
                url=url,
                published_at=row.get("published_date"),
                source=row.get("source") or _source_from_url(url),
                summary=summary,
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
    ttl_seconds = _ttl_seconds(data)
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    await upsert_company_provider_result(
        company=data.company,
        provider="recent_news",
        result=output.model_dump(mode="json"),
        ttl_seconds=ttl_seconds,
        request=data.model_dump(mode="json"),
    )
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


def _news_summary_prompt(
    *,
    title: str,
    source: str | None,
    published_at: str | None,
    content: str,
) -> str:
    return (
        "Summarize this news item in 1-2 sentences for an interview prep brief.\n"
        f"Title: {title}\n"
        f"Source: {source or 'unknown'}\n"
        f"Published: {published_at or 'unknown'}\n"
        f"Text: {content[:3000]}"
    )


def _ttl_seconds(data: RecentNewsInput) -> int:
    return 3600 if data.days <= 7 else 6 * 3600
