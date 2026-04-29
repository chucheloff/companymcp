import hashlib
import json
from urllib.parse import urlparse

import httpx

from company_mcp.cache.company_table import upsert_company_provider_result
from company_mcp.cache.store import get_json, get_ttl, set_json
from company_mcp.config import settings
from company_mcp.mcp.schemas import (
    LinkedInCompanyLookupInput,
    LinkedInCompanyLookupOutput,
    LinkedInCompanyMatch,
)
from company_mcp.models.openrouter import OpenRouterClient, OpenRouterUnavailable
from company_mcp.providers.tavily_news import tavily_search


async def lookup_linkedin_company(data: LinkedInCompanyLookupInput) -> LinkedInCompanyLookupOutput:
    query = _build_query(data)
    cache_key = _cache_key(data, query)
    cached = None if data.force_refresh else await get_json(cache_key)
    if cached:
        output = LinkedInCompanyLookupOutput.model_validate(cached)
        await upsert_company_provider_result(
            company=data.company,
            provider="linkedin_company_lookup",
            result=output.model_dump(mode="json"),
            ttl_seconds=await get_ttl(cache_key) or _ttl_seconds(output),
            request=data.model_dump(mode="json"),
        )
        return output

    if not settings.tavily_api_key:
        return LinkedInCompanyLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=["TAVILY_API_KEY is not configured."],
        )

    try:
        result_json = await tavily_search(query=query, topic="general", limit=data.limit * 2)
    except httpx.HTTPStatusError as exc:
        return LinkedInCompanyLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Tavily HTTP {exc.response.status_code} while searching LinkedIn companies."],
        )
    except Exception as exc:
        return LinkedInCompanyLookupOutput(
            matches=[],
            query_used=query,
            confidence=0.0,
            warnings=[f"Failed to search LinkedIn company snippets: {exc}"],
        )

    rows = result_json.get("results", [])
    normalized = await _normalize_company_candidates(data, rows)
    warnings = ["LinkedIn company data is search-result-derived; details may be incomplete."]
    if normalized is None and settings.openrouter_api_key:
        warnings.append("OpenRouter LinkedIn company normalization failed; using raw snippets.")

    matches: list[LinkedInCompanyMatch] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        url = (row.get("url") or "").strip()
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        if not _is_public_linkedin_company(url) or url in seen:
            continue
        seen.add(url)
        normalized_candidate = normalized.get(str(index), {}) if normalized else {}
        confidence, evidence = _score_company_match(data, title, content, url, normalized_candidate)
        matches.append(
            LinkedInCompanyMatch(
                name=_clean_optional_string(normalized_candidate.get("name"))
                or _display_name_from_title(title)
                or data.company,
                linkedin_url=url,
                description=_clean_optional_string(normalized_candidate.get("description"))
                or content[:280]
                or None,
                website=_clean_optional_string(normalized_candidate.get("website")),
                industry=_clean_optional_string(normalized_candidate.get("industry")),
                size=_clean_optional_string(normalized_candidate.get("size")),
                confidence=confidence,
                evidence=evidence,
            )
        )

    matches.sort(key=lambda item: item.confidence, reverse=True)
    matches = matches[: data.limit]
    if not matches:
        warnings.append("No public LinkedIn company candidates found.")

    output = LinkedInCompanyLookupOutput(
        matches=matches,
        query_used=query,
        confidence=matches[0].confidence if matches else 0.0,
        warnings=warnings,
    )
    ttl_seconds = _ttl_seconds(output)
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    await upsert_company_provider_result(
        company=data.company,
        provider="linkedin_company_lookup",
        result=output.model_dump(mode="json"),
        ttl_seconds=ttl_seconds,
        request=data.model_dump(mode="json"),
    )
    return output


def _build_query(data: LinkedInCompanyLookupInput) -> str:
    parts = [f'"{data.company}"', "site:linkedin.com/company"]
    if data.domain:
        parts.append(f'"{data.domain}"')
    return " ".join(parts)


def _cache_key(data: LinkedInCompanyLookupInput, query: str) -> str:
    payload = {
        "query": query,
        "limit": data.limit,
        "company": data.company.strip().lower(),
        "domain": (data.domain or "").strip().lower(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    company_key = _cache_component(data.company)
    domain_key = _cache_component(data.domain or "unknown")
    return f"linkedin_company_lookup:v2:{company_key}:{domain_key}:{digest}"


def _is_public_linkedin_company(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return _is_linkedin_hostname(hostname) and parsed.path.startswith("/company/")


def _is_linkedin_hostname(hostname: str) -> bool:
    return hostname == "linkedin.com" or hostname.endswith(".linkedin.com")


def _score_company_match(
    data: LinkedInCompanyLookupInput,
    title: str,
    content: str,
    url: str,
    normalized: dict,
) -> tuple[float, list[str]]:
    normalized_text = " ".join(
        item
        for item in [
            normalized.get("name") or "",
            normalized.get("description") or "",
            normalized.get("website") or "",
            normalized.get("industry") or "",
            normalized.get("size") or "",
        ]
        if isinstance(item, str)
    )
    haystack = f"{title} {content} {url} {normalized_text}".lower()
    company_haystack = f"{title} {content} {normalized_text}".lower()
    if data.domain:
        company_haystack = company_haystack.replace(data.domain.lower(), "")
    company_tokens = [part.lower() for part in data.company.split() if part.strip()]
    evidence: list[str] = []
    score = 0.15

    if company_tokens and all(token in company_haystack for token in company_tokens):
        score += 0.35
        evidence.append("company tokens matched search result")
    else:
        score = min(score, 0.35)
        evidence.append("requested company not confirmed")

    if data.domain and data.domain.lower() in haystack:
        score += 0.2
        evidence.append("domain matched search result")

    if "linkedin.com/company/" in url:
        score += 0.15
        evidence.append("public LinkedIn company URL")

    if normalized:
        score += 0.05
        evidence.append("snippet normalized by light model")

    return max(0.0, min(score, 0.95)), evidence


async def _normalize_company_candidates(
    data: LinkedInCompanyLookupInput,
    rows: list[dict],
) -> dict[str, dict] | None:
    if not settings.openrouter_api_key:
        return None

    candidates = []
    for index, row in enumerate(rows[: data.limit * 2]):
        url = (row.get("url") or "").strip()
        if not _is_public_linkedin_company(url):
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
        "Normalize these LinkedIn company search snippets. Do not browse LinkedIn. "
        "Return JSON with key candidates, where each item has index, name, description, "
        "website, industry, size. Use null for unknown fields.\n\n"
        f"Requested company: {data.company}\n"
        f"Requested domain: {data.domain or 'unknown'}\n"
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


def _display_name_from_title(title: str) -> str | None:
    if not title:
        return None
    value = title.split("|", 1)[0].split(" - ", 1)[0].strip()
    return value or None


def _clean_optional_string(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower() in {"null", "none", "unknown"}:
        return None
    return value


def _ttl_seconds(output: LinkedInCompanyLookupOutput) -> int:
    if not output.matches:
        return 3600
    if output.confidence < 0.5:
        return 3600
    if output.confidence < 0.7:
        return 24 * 3600
    return 7 * 24 * 3600


def _cache_component(value: str) -> str:
    normalized = "-".join(value.strip().lower().replace("_", "-").split())
    return normalized or "unknown"
