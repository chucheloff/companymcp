from urllib.parse import quote

import httpx

from company_mcp.cache.company_table import upsert_company_provider_result
from company_mcp.cache.store import get_json, get_ttl, set_json
from company_mcp.mcp.schemas import WikipediaCompanyInput, WikipediaCompanyOutput

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"


async def lookup_wikipedia_company(data: WikipediaCompanyInput) -> WikipediaCompanyOutput:
    cache_key = _cache_key(data)
    cached = await get_json(cache_key)
    if cached:
        output = WikipediaCompanyOutput.model_validate(cached)
        await upsert_company_provider_result(
            company=data.company,
            provider="wikipedia_company",
            result=output.model_dump(mode="json"),
            ttl_seconds=await get_ttl(cache_key) or _ttl_seconds(output),
            request=data.model_dump(mode="json"),
        )
        return output

    warnings: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            title = await _search_title(client, data.company)
            if not title:
                output = WikipediaCompanyOutput(
                    confidence=0.0,
                    warnings=["No likely Wikipedia page found for company."],
                )
                await _cache_and_upsert(data, cache_key, output)
                return output

            response = await client.get(f"{WIKIPEDIA_REST_SUMMARY_URL}/{quote(title, safe='')}")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        output = WikipediaCompanyOutput(
            confidence=0.0,
            warnings=[f"Wikipedia HTTP {exc.response.status_code}."],
        )
        await _cache_and_upsert(data, cache_key, output)
        return output
    except Exception as exc:
        output = WikipediaCompanyOutput(
            confidence=0.0,
            warnings=[f"Failed to fetch Wikipedia summary: {exc}"],
        )
        await _cache_and_upsert(data, cache_key, output)
        return output

    page_title = payload.get("title")
    summary = payload.get("extract")
    description = payload.get("description")
    page_url = (payload.get("content_urls") or {}).get("desktop", {}).get("page")
    confidence = _confidence(data.company, page_title, summary, description)
    if confidence < 0.5:
        warnings.append("Wikipedia result may not refer to the requested company.")

    output = WikipediaCompanyOutput(
        title=page_title,
        url=page_url,
        summary=summary,
        description=description,
        confidence=confidence,
        warnings=warnings,
    )
    await _cache_and_upsert(data, cache_key, output)
    return output


async def _search_title(client: httpx.AsyncClient, company: str) -> str | None:
    response = await client.get(
        WIKIPEDIA_API_URL,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f'"{company}" company',
            "srlimit": 3,
            "format": "json",
            "origin": "*",
        },
    )
    response.raise_for_status()
    rows = response.json().get("query", {}).get("search", [])
    if not rows:
        return None
    company_tokens = _tokens(company)
    for row in rows:
        title = str(row.get("title") or "")
        title_tokens = _tokens(title)
        if company_tokens and company_tokens.issubset(title_tokens):
            return title
    return str(rows[0].get("title") or "") or None


async def _cache_and_upsert(
    data: WikipediaCompanyInput,
    cache_key: str,
    output: WikipediaCompanyOutput,
) -> None:
    ttl_seconds = _ttl_seconds(output)
    await set_json(cache_key, output.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    await upsert_company_provider_result(
        company=data.company,
        provider="wikipedia_company",
        result=output.model_dump(mode="json"),
        ttl_seconds=ttl_seconds,
        request=data.model_dump(mode="json"),
    )


def _cache_key(data: WikipediaCompanyInput) -> str:
    company = data.company.strip().lower()
    domain = (data.domain or "").strip().lower()
    return f"wikipedia_company:v1:{company}:{domain}"


def _confidence(company: str, title: str | None, summary: str | None, description: str | None) -> float:
    if not title or not summary:
        return 0.0

    company_tokens = _tokens(company)
    haystack = " ".join(item for item in [title, summary, description] if item).lower()
    score = 0.25
    if company_tokens and company_tokens.issubset(_tokens(title)):
        score += 0.35
    elif company_tokens and all(token in haystack for token in company_tokens):
        score += 0.2

    company_markers = ["company", "startup", "corporation", "inc.", "inc", "llc", "technology"]
    if any(marker in haystack for marker in company_markers):
        score += 0.2

    return min(score, 0.9)


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in value.lower().replace("-", " ").replace("_", " ").split()
        if token and token not in {"the", "inc", "llc", "ltd", "corp", "corporation", "company"}
    }


def _ttl_seconds(output: WikipediaCompanyOutput) -> int:
    if output.confidence < 0.5:
        return 24 * 3600
    return 30 * 24 * 3600
