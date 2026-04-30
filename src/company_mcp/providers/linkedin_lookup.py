import hashlib
import json
from urllib.parse import urlparse

import httpx

from company_mcp.cache.company_table import upsert_company_provider_result
from company_mcp.cache.store import get_json, get_ttl, set_json
from company_mcp.config import settings
from company_mcp.mcp.schemas import LinkedInLookupInput, LinkedInLookupOutput, LinkedInMatch
from company_mcp.models.openrouter import (
    OpenRouterClient,
    OpenRouterUnavailable,
    is_enabled as openrouter_enabled,
)
from company_mcp.providers.tavily_news import tavily_search


async def lookup_linkedin(data: LinkedInLookupInput) -> LinkedInLookupOutput:
    query = _build_query(data)
    cache_key = _cache_key(data, query)
    cached = None if data.force_refresh else await get_json(cache_key)
    if cached:
        output = LinkedInLookupOutput.model_validate(cached)
        await upsert_company_provider_result(
            company=data.company,
            provider="linkedin_people_lookup",
            result=output.model_dump(mode="json"),
            ttl_seconds=await get_ttl(cache_key) or _ttl_seconds(output),
            request=data.model_dump(mode="json"),
        )
        return output

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

    warnings = ["LinkedIn data is search-result-derived; profile details may be incomplete."]
    rows = result_json.get("results", [])
    normalized = await _normalize_candidates(data, rows)
    if normalized is None and data.use_openrouter and openrouter_enabled() and settings.openrouter_api_key:
        warnings.append("OpenRouter LinkedIn snippet normalization failed; using raw snippets.")

    matches: list[LinkedInMatch] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        if not _is_public_linkedin_profile(url) or url in seen:
            continue
        seen.add(url)
        normalized_candidate = normalized.get(str(index), {}) if normalized else {}
        confidence, evidence, company_match = _score_match(
            data,
            title,
            content,
            url,
            normalized_candidate,
        )
        display_name = (
            _clean_optional_string(normalized_candidate.get("name"))
            or _display_name_from_title(title)
            or data.name
        )
        headline = _clean_optional_string(normalized_candidate.get("headline")) or title or content[:160] or None
        matches.append(
            LinkedInMatch(
                name=display_name,
                headline=headline,
                title=_clean_optional_string(normalized_candidate.get("title")),
                current_company=_clean_optional_string(normalized_candidate.get("current_company")),
                url=url,
                company_match=company_match,
                confidence=confidence,
                evidence=evidence,
            )
        )

    matches.sort(key=lambda item: item.confidence, reverse=True)
    matches = matches[: data.limit]
    if not matches:
        warnings.append("No public LinkedIn profile candidates found.")

    output = LinkedInLookupOutput(
        matches=matches,
        query_used=query,
        confidence=matches[0].confidence if matches else 0.0,
        warnings=warnings,
    )
    ttl_seconds = _ttl_seconds(output)
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    await upsert_company_provider_result(
        company=data.company,
        provider="linkedin_people_lookup",
        result=output.model_dump(mode="json"),
        ttl_seconds=ttl_seconds,
        request=data.model_dump(mode="json"),
    )
    return output


def _cache_key(data: LinkedInLookupInput, query: str) -> str:
    payload = {
        "query": query,
        "limit": data.limit,
        "name": data.name.strip().lower(),
        "company": (data.company or "").strip().lower(),
        "title_hint": (data.title_hint or "").strip().lower(),
        "use_openrouter": data.use_openrouter,
        "openrouter_enabled": openrouter_enabled(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    name_key = _cache_component(data.name)
    company_key = _cache_component(data.company or "unknown")
    return f"linkedin_lookup:v3:{name_key}:{company_key}:{digest}"


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
    return _is_linkedin_hostname(hostname) and parsed.path.startswith("/in/")


def _is_linkedin_hostname(hostname: str) -> bool:
    return hostname == "linkedin.com" or hostname.endswith(".linkedin.com")


def _score_match(
    data: LinkedInLookupInput,
    title: str,
    content: str,
    url: str,
    normalized: dict,
) -> tuple[float, list[str], bool]:
    normalized_name = _clean_optional_string(normalized.get("name"))
    normalized_title = _clean_optional_string(normalized.get("title"))
    normalized_company = _clean_optional_string(normalized.get("current_company"))
    normalized_headline = _clean_optional_string(normalized.get("headline"))
    haystack = " ".join(
        item
        for item in [
            title,
            content,
            url,
            normalized_name or "",
            normalized_title or "",
            normalized_company or "",
            normalized_headline or "",
        ]
        if item
    ).lower()
    name_tokens = [part.lower() for part in data.name.split() if part.strip()]
    evidence: list[str] = []
    score = 0.15
    name_match = bool(name_tokens and all(token in haystack for token in name_tokens))
    if name_match:
        score += 0.35
        evidence.append("name tokens matched search result")
    elif name_tokens and _slug_matches_name(url, name_tokens):
        name_match = True
        score += 0.3
        evidence.append("profile URL slug matched name tokens")

    company_match = False
    if data.company and data.company.lower() in haystack:
        company_match = True
        score += 0.2 if name_match else 0.1
        evidence.append("company matched search result")

    if data.title_hint and data.title_hint.lower() in haystack:
        score += 0.15 if name_match else 0.05
        evidence.append("title hint matched search result")

    if "linkedin.com/in/" in url:
        score += 0.1
        evidence.append("public LinkedIn profile URL")

    if normalized:
        score += 0.05
        evidence.append("snippet normalized by light model")

    if data.company and normalized_company and data.company.lower() not in normalized_company.lower():
        score -= 0.15
        evidence.append("normalized company did not match requested company")

    if data.title_hint and normalized_title and data.title_hint.lower() not in normalized_title.lower():
        score -= 0.05
        evidence.append("normalized title did not match title hint")

    if not name_match:
        score = min(score, 0.4)
        evidence.append("requested name not confirmed")

    return max(0.0, min(score, 0.95)), evidence, company_match


def _display_name_from_title(title: str) -> str | None:
    if not title:
        return None
    value = title.split("|", 1)[0].split(" - ", 1)[0].strip()
    return value or None


async def _normalize_candidates(
    data: LinkedInLookupInput,
    rows: list[dict],
) -> dict[str, dict] | None:
    if not data.use_openrouter or not openrouter_enabled() or not settings.openrouter_api_key:
        return None

    candidates = []
    for index, row in enumerate(rows[: data.limit * 2]):
        url = (row.get("url") or "").strip()
        if not _is_public_linkedin_profile(url):
            continue
        candidates.append(
            {
                "index": str(index),
                "title": (row.get("title") or "").strip()[:300],
                "url": url,
                "snippet": (row.get("content") or "").strip()[:700],
            }
        )
    if not candidates:
        return {}

    prompt = (
        "Normalize these LinkedIn search snippets. Do not browse LinkedIn. "
        "Return JSON with key candidates, where each item has index, name, headline, "
        "title, current_company. Use null for unknown fields.\n\n"
        f"Requested person: {data.name}\n"
        f"Requested company: {data.company or 'unknown'}\n"
        f"Requested title hint: {data.title_hint or 'unknown'}\n"
        f"Candidates: {json.dumps(candidates, ensure_ascii=True)}"
    )
    try:
        raw = await OpenRouterClient().extract_json(prompt, task="linkedin_lookup")
    except (OpenRouterUnavailable, Exception):
        return None

    normalized: dict[str, dict] = {}
    for item in raw.get("candidates", []):
        if not isinstance(item, dict):
            continue
        index = str(item.get("index") or "")
        if index:
            normalized[index] = item
    return normalized


def _clean_optional_string(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower() in {"null", "none", "unknown"}:
        return None
    return value


def _slug_matches_name(url: str, name_tokens: list[str]) -> bool:
    path = urlparse(url).path.lower()
    return all(token in path for token in name_tokens)


def _cache_component(value: str) -> str:
    normalized = "-".join(value.strip().lower().replace("_", "-").split())
    return normalized or "unknown"


def _ttl_seconds(output: LinkedInLookupOutput) -> int:
    if not output.matches:
        return 3600
    if output.confidence < 0.5:
        return 3600
    if output.confidence < 0.7:
        return 24 * 3600
    return 7 * 24 * 3600
