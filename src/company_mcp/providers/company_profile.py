import re
from html import unescape
from urllib.parse import urlparse

import httpx

from company_mcp.cache.store import get_json, set_json
from company_mcp.mcp.schemas import CompanyPayload, CompanyProfileInput, CompanyProfileOutput, SourceEvidence


def _normalize_domain(domain: str) -> str:
    candidate = domain.strip().lower()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        return parsed.netloc or parsed.path
    return candidate


async def build_company_profile(data: CompanyProfileInput) -> CompanyProfileOutput:
    normalized_domain = _normalize_domain(data.domain)
    cache_key = f"company_profile:v1:{normalized_domain}"
    cached = await get_json(cache_key)
    if cached:
        return CompanyProfileOutput.model_validate(cached)

    homepage = f"https://{normalized_domain}"
    candidates = [homepage, f"{homepage}/about", f"{homepage}/careers", f"{homepage}/team"]
    selected_urls = candidates[: data.max_pages]

    warnings: list[str] = []
    sources: list[SourceEvidence] = []
    combined_text: list[str] = []

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for url in selected_urls:
            try:
                response = await client.get(url)
                if response.status_code >= 400:
                    warnings.append(f"Skipped {url}: HTTP {response.status_code}.")
                    continue
                html_text = response.text
                title = _extract_title(html_text) or f"{normalized_domain} page"
                description = _extract_meta_description(html_text)
                evidence = description or "Fetched page successfully."
                sources.append(SourceEvidence(url=str(response.url), title=title, evidence=evidence))
                combined_text.append(" ".join(filter(None, [title, description])))
            except Exception:
                warnings.append(f"Failed to fetch {url}.")

    if not sources:
        payload = CompanyPayload(
            name=normalized_domain.split(".")[0].replace("-", " ").title(),
            domain=normalized_domain,
            description="No reachable pages for profile extraction.",
            careers_url=f"{homepage}/careers",
        )
        result = CompanyProfileOutput(
            company=payload,
            confidence=0.05,
            sources=[],
            warnings=warnings + ["No evidence found; returning empty profile scaffold."],
        )
        await set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=3600)
        return result

    summary = " ".join(combined_text).strip()
    summary = summary[:600] if summary else None

    payload = CompanyPayload(
        name=normalized_domain.split(".")[0].replace("-", " ").title(),
        domain=normalized_domain,
        description=summary or "Profile extracted from public company pages.",
        careers_url=f"{homepage}/careers",
    )

    result = CompanyProfileOutput(
        company=payload,
        confidence=0.35 if len(sources) == 1 else 0.55,
        sources=sources,
        warnings=warnings,
    )
    ttl_seconds = max(3600, data.freshness_hours * 3600)
    await set_json(cache_key, result.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    return result


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
    return value or None


def _extract_meta_description(html: str) -> str | None:
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    value = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
    return value or None
