import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from company_mcp.cache.company_table import get_company_provider_results, upsert_company_provider_result
from company_mcp.mcp.schemas import (
    CompanyOverviewBrief,
    CompanyOverviewInput,
    CompanyOverviewOutput,
    CompanyPayload,
    CompanyProfileInput,
    LinkedInCompanyLookupInput,
    RecentNewsInput,
    SourceEvidence,
    WikipediaCompanyInput,
)
from company_mcp.models.openrouter import OpenRouterClient, OpenRouterUnavailable
from company_mcp.providers.company_profile import build_company_profile
from company_mcp.providers.linkedin_company_lookup import lookup_linkedin_company
from company_mcp.providers.tavily_news import fetch_recent_news
from company_mcp.providers.wikipedia_company import lookup_wikipedia_company

OVERVIEW_PROVIDER = "company_overview"
OVERVIEW_TTL_SECONDS = 24 * 3600


async def build_company_overview(data: CompanyOverviewInput) -> CompanyOverviewOutput:
    profile_task = None
    if data.domain:
        profile_task = build_company_profile(
            CompanyProfileInput(domain=data.domain, max_pages=data.max_pages)
        )

    tasks = [
        fetch_recent_news(
            RecentNewsInput(
                company=data.company,
                domain=data.domain,
                days=data.days,
                limit=data.news_limit,
            )
        ),
        lookup_linkedin_company(
            LinkedInCompanyLookupInput(company=data.company, domain=data.domain, limit=3)
        ),
    ]
    if profile_task:
        tasks.append(profile_task)
    if data.include_wikipedia:
        tasks.append(lookup_wikipedia_company(WikipediaCompanyInput(company=data.company, domain=data.domain)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    providers, warnings = _collect_provider_results(results)
    cached_providers = await get_company_provider_results(data.company)
    if cached_providers:
        providers["cached_company_results"] = _cached_provider_snapshot(cached_providers)

    company = _company_payload(data, providers)
    sources = _sources(providers)
    overview, synthesis_warnings = await _synthesize_overview(data, company, providers)
    warnings.extend(synthesis_warnings)

    output = CompanyOverviewOutput(
        company=company,
        overview=overview,
        providers=providers,
        sources=sources,
        confidence=_confidence(providers, overview),
        warnings=list(dict.fromkeys(warnings)),
    )
    await upsert_company_provider_result(
        company=data.company,
        provider=OVERVIEW_PROVIDER,
        result=_cacheable_overview_result(output),
        ttl_seconds=OVERVIEW_TTL_SECONDS,
        request=data.model_dump(mode="json"),
    )
    return output


def _collect_provider_results(results: list[Any]) -> tuple[dict[str, Any], list[str]]:
    providers: dict[str, Any] = {}
    warnings: list[str] = []
    for result in results:
        if isinstance(result, Exception):
            warnings.append(f"Provider failed: {type(result).__name__}: {result}")
            continue

        name = _provider_name(result)
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        providers[name] = payload
        warnings.extend(payload.get("warnings") or [])
    return providers, warnings


def _cached_provider_snapshot(cached: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_key": cached.get("company_key"),
        "updated_at": cached.get("updated_at"),
        "providers": {
            name: {
                "cached_at": entry.get("cached_at"),
                "expires_at": entry.get("expires_at"),
                "ttl_seconds": entry.get("ttl_seconds"),
                "request": entry.get("request") or {},
            }
            for name, entry in (cached.get("providers") or {}).items()
            if isinstance(entry, dict) and name != OVERVIEW_PROVIDER
        },
    }


def _cacheable_overview_result(output: CompanyOverviewOutput) -> dict[str, Any]:
    payload = output.model_dump(mode="json")
    providers = payload.get("providers") or {}
    providers.pop("cached_company_results", None)
    payload["providers"] = providers
    return payload


def _provider_name(result: Any) -> str:
    class_name = result.__class__.__name__
    if class_name == "CompanyProfileOutput":
        return "company_profile"
    if class_name == "RecentNewsOutput":
        return "recent_news"
    if class_name == "LinkedInCompanyLookupOutput":
        return "linkedin_company_lookup"
    if class_name == "WikipediaCompanyOutput":
        return "wikipedia_company"
    return class_name


async def _synthesize_overview(
    data: CompanyOverviewInput,
    company: CompanyPayload,
    providers: dict[str, Any],
) -> tuple[CompanyOverviewBrief, list[str]]:
    if not providers:
        return _fallback_overview(company, providers), ["No provider results available for synthesis."]

    prompt = (
        "Create a source-grounded company overview for interview preparation. "
        "Use only the provider data below. If facts conflict or are missing, call that out. "
        "Keep the JSON compact: summary under 120 words, each list at most 5 items, "
        "and each list item under 25 words. "
        "Return JSON with keys: summary, what_they_do, market_position, products, "
        "recent_developments, interview_angles, uncertainties.\n\n"
        f"Requested company: {data.company}\n"
        f"Requested domain: {data.domain or 'unknown'}\n"
        f"Normalized company payload: {company.model_dump_json()}\n"
        f"Provider data: {json.dumps(_trim_for_prompt(providers), ensure_ascii=True)}"
    )
    try:
        raw = await OpenRouterClient().synthesize_json(prompt)
        return CompanyOverviewBrief.model_validate(_coerce_brief_payload(raw)), []
    except OpenRouterUnavailable as exc:
        return _fallback_overview(company, providers), [str(exc)]
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return _fallback_overview(company, providers), [f"OpenRouter final brief synthesis failed: {exc}"]
    except Exception as exc:
        return _fallback_overview(company, providers), [
            f"OpenRouter final brief synthesis failed: {type(exc).__name__}: {exc}"
        ]


def _fallback_overview(company: CompanyPayload, providers: dict[str, Any]) -> CompanyOverviewBrief:
    news_items = (providers.get("recent_news") or {}).get("items") or []
    recent_developments = [
        item.get("summary") or item.get("title")
        for item in news_items[:5]
        if item.get("summary") or item.get("title")
    ]
    uncertainties: list[str] = []
    if not providers.get("company_profile"):
        uncertainties.append("Company profile pages were not available or not requested.")
    if not providers.get("wikipedia_company"):
        uncertainties.append("Wikipedia summary was not available or not requested.")

    return CompanyOverviewBrief(
        summary=company.description or f"{company.name} is a company associated with {company.domain}.",
        what_they_do=company.description,
        products=company.products,
        recent_developments=recent_developments,
        interview_angles=_interview_angles(company, recent_developments),
        uncertainties=uncertainties,
    )


def _coerce_brief_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    for key in ["summary", "what_they_do", "market_position"]:
        value = payload.get(key)
        if isinstance(value, list):
            payload[key] = " ".join(str(item).strip() for item in value if str(item).strip())
    for key in ["products", "recent_developments", "interview_angles", "uncertainties"]:
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, str):
            payload[key] = [value]
        elif isinstance(value, list):
            payload[key] = [str(item).strip() for item in value if str(item).strip()]
    return payload


def _company_payload(data: CompanyOverviewInput, providers: dict[str, Any]) -> CompanyPayload:
    profile = providers.get("company_profile") or {}
    profile_company = profile.get("company") or {}
    linkedin_matches = (providers.get("linkedin_company_lookup") or {}).get("matches") or []
    linkedin_top = linkedin_matches[0] if linkedin_matches else {}
    wiki = providers.get("wikipedia_company") or {}

    name = profile_company.get("name") or linkedin_top.get("name") or wiki.get("title") or data.company
    domain = profile_company.get("domain") or data.domain or linkedin_top.get("website") or ""
    description = profile_company.get("description") or linkedin_top.get("description") or wiki.get("summary")

    return CompanyPayload(
        name=name,
        domain=domain,
        description=description,
        industry=profile_company.get("industry") or linkedin_top.get("industry"),
        products=profile_company.get("products") or [],
        hq=profile_company.get("hq"),
        size=profile_company.get("size") or linkedin_top.get("size"),
        careers_url=profile_company.get("careers_url"),
        linkedin_url=profile_company.get("linkedin_url") or linkedin_top.get("linkedin_url"),
    )


def _sources(providers: dict[str, Any]) -> list[SourceEvidence]:
    now = datetime.now(UTC)
    sources: list[SourceEvidence] = []
    for item in (providers.get("company_profile") or {}).get("sources") or []:
        try:
            sources.append(SourceEvidence.model_validate(item))
        except ValidationError:
            continue

    wiki = providers.get("wikipedia_company") or {}
    if wiki.get("url"):
        sources.append(
            SourceEvidence(
                url=wiki["url"],
                title=wiki.get("title") or "Wikipedia",
                retrieved_at=now,
                evidence=wiki.get("summary") or "Wikipedia summary page.",
            )
        )

    for item in ((providers.get("recent_news") or {}).get("items") or [])[:5]:
        if item.get("url"):
            sources.append(
                SourceEvidence(
                    url=item["url"],
                    title=item.get("title") or "News result",
                    retrieved_at=now,
                    evidence=item.get("summary") or item.get("source") or "Recent news result.",
                )
            )
    return sources[:12]


def _confidence(providers: dict[str, Any], overview: CompanyOverviewBrief) -> float:
    scores: list[float] = []
    for provider in ["company_profile", "recent_news", "linkedin_company_lookup", "wikipedia_company"]:
        value = providers.get(provider)
        if value and isinstance(value.get("confidence"), (int, float)):
            scores.append(float(value["confidence"]))
    if not scores:
        return 0.25 if overview.summary else 0.0
    return min(0.95, (sum(scores) / len(scores)) + min(len(scores), 4) * 0.05)


def _interview_angles(company: CompanyPayload, recent_developments: list[str]) -> list[str]:
    angles = []
    if company.products:
        angles.append(f"How {company.name}'s product portfolio is evolving.")
    if company.industry:
        angles.append(f"Competitive dynamics in {company.industry}.")
    if recent_developments:
        angles.append("How recent company news affects priorities for the role.")
    return angles[:4]


def _trim_for_prompt(providers: dict[str, Any]) -> dict[str, Any]:
    trimmed = json.loads(json.dumps(providers))
    cached = trimmed.get("cached_company_results")
    if isinstance(cached, dict):
        cached["providers"] = {
            name: {
                "cached_at": entry.get("cached_at"),
                "expires_at": entry.get("expires_at"),
                "request": entry.get("request"),
            }
            for name, entry in (cached.get("providers") or {}).items()
            if isinstance(entry, dict)
        }

    news = trimmed.get("recent_news")
    if isinstance(news, dict):
        news["items"] = (news.get("items") or [])[:5]

    return trimmed
