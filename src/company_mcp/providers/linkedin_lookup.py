from urllib.parse import urlparse

import httpx

from company_mcp.cache.store import get_json, set_json
from company_mcp.config import settings
from company_mcp.mcp.schemas import LinkedInLookupInput, LinkedInLookupOutput, LinkedInMatch
from company_mcp.providers.tavily_news import tavily_search


async def lookup_linkedin(data: LinkedInLookupInput) -> LinkedInLookupOutput:
    query = _build_query(data)
    cache_key = f"linkedin_lookup:v1:{query}:{data.limit}"
    cached = await get_json(cache_key)
    if cached:
        return LinkedInLookupOutput.model_validate(cached)

    if not settings.tavily_api_key:
        return LinkedInLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=["TAVILY_API_KEY is not configured."],
        )

    try:
        result_json = await tavily_search(query=query, topic="general", limit=data.limit * 2)
    except httpx.HTTPStatusError as exc:
        return LinkedInLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Tavily HTTP {exc.response.status_code} while searching LinkedIn."],
        )
    except Exception as exc:
        return LinkedInLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Failed to search LinkedIn snippets: {exc}"],
        )

    matches: list[LinkedInMatch] = []
    seen: set[str] = set()
    for row in result_json.get("results", []):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        if not _is_public_linkedin_profile(url) or url in seen:
            continue
        seen.add(url)
        confidence, evidence, company_match = _score_match(data, title, content, url)
        matches.append(
            LinkedInMatch(
                name=_display_name_from_title(title) or data.name,
                headline=title or content[:160] or None,
                url=url,
                company_match=company_match,
                confidence=confidence,
                evidence=evidence,
            )
        )

    matches.sort(key=lambda item: item.confidence, reverse=True)
    matches = matches[: data.limit]
    warnings = ["LinkedIn data is search-result-derived; profile details may be incomplete."]
    if not matches:
        warnings.append("No public LinkedIn profile candidates found.")

    output = LinkedInLookupOutput(
        matches=matches,
        query_used=query,
        confidence=matches[0].confidence if matches else 0.0,
        warnings=warnings,
    )
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=7 * 24 * 3600)
    return output


def _build_query(data: LinkedInLookupInput) -> str:
    parts = [f'"{data.name}"', "site:linkedin.com/in"]
    if data.company:
        parts.append(f'"{data.company}"')
    if data.title_hint:
        parts.append(f'"{data.title_hint}"')
    return " ".join(parts)


def _is_public_linkedin_profile(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return hostname.endswith("linkedin.com") and parsed.path.startswith("/in/")


def _score_match(
    data: LinkedInLookupInput,
    title: str,
    content: str,
    url: str,
) -> tuple[float, list[str], bool]:
    haystack = f"{title} {content} {url}".lower()
    name_tokens = [part.lower() for part in data.name.split() if part.strip()]
    evidence: list[str] = []
    score = 0.15
    if name_tokens and all(token in haystack for token in name_tokens):
        score += 0.35
        evidence.append("name tokens matched search result")

    company_match = False
    if data.company and data.company.lower() in haystack:
        company_match = True
        score += 0.25
        evidence.append("company matched search result")

    if data.title_hint and data.title_hint.lower() in haystack:
        score += 0.15
        evidence.append("title hint matched search result")

    if "linkedin.com/in/" in url:
        score += 0.1
        evidence.append("public LinkedIn profile URL")

    return min(score, 0.95), evidence, company_match


def _display_name_from_title(title: str) -> str | None:
    if not title:
        return None
    value = title.split("|", 1)[0].split(" - ", 1)[0].strip()
    return value or None
