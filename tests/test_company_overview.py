from datetime import UTC, datetime, timedelta

import pytest

from company_mcp.mcp.schemas import (
    CompanyOverviewBrief,
    CompanyOverviewInput,
    CompanyOverviewOutput,
    CompanyProfileOutput,
    CompanyPayload,
    LinkedInCompanyLookupOutput,
    LinkedInCompanyMatch,
    RecentNewsItem,
    RecentNewsOutput,
    SourceEvidence,
    WikipediaCompanyOutput,
)
from company_mcp.providers import company_overview


@pytest.mark.anyio
async def test_company_overview_reuses_matching_cached_result(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = CompanyOverviewInput(company="OpenAI", domain="openai.com")
    cached_output = CompanyOverviewOutput(
        company=CompanyPayload(
            name="OpenAI",
            domain="openai.com",
            description="Cached overview.",
        ),
        overview=CompanyOverviewBrief(
            summary="Cached overview.",
            what_they_do="Cached overview.",
        ),
        providers={},
        confidence=0.8,
    )

    async def fake_get_company_provider_results(_company):
        return {
            "company_key": "openai",
            "providers": {
                "company_overview": {
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "request": payload.model_dump(mode="json"),
                    "result": cached_output.model_dump(mode="json"),
                }
            },
        }

    async def fail_provider(*_args, **_kwargs):
        raise AssertionError("Provider should not be called on matching overview cache hit")

    monkeypatch.setattr(company_overview, "get_company_provider_results", fake_get_company_provider_results)
    monkeypatch.setattr(company_overview, "fetch_recent_news", fail_provider)
    monkeypatch.setattr(company_overview, "lookup_linkedin_company", fail_provider)
    monkeypatch.setattr(company_overview, "build_company_profile", fail_provider)
    monkeypatch.setattr(company_overview, "lookup_wikipedia_company", fail_provider)

    result = await company_overview.build_company_overview(payload)

    assert result.overview.summary == "Cached overview."
    assert result.confidence == 0.8


@pytest.mark.anyio
async def test_company_overview_uses_final_brief_synthesis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    async def fake_fetch_recent_news(_data):
        return RecentNewsOutput(
            items=[
                RecentNewsItem(
                    title="OpenAI launches a product",
                    url="https://example.com/news",
                    summary="OpenAI launched a product.",
                )
            ],
            query_used="OpenAI company news",
            confidence=0.7,
        )

    async def fake_lookup_linkedin_company(_data):
        return LinkedInCompanyLookupOutput(
            matches=[
                LinkedInCompanyMatch(
                    name="OpenAI",
                    linkedin_url="https://www.linkedin.com/company/openai",
                    website="openai.com",
                    industry="Artificial intelligence",
                    confidence=0.9,
                )
            ],
            query_used="OpenAI LinkedIn",
            confidence=0.9,
        )

    async def fake_build_company_profile(_data):
        return CompanyProfileOutput(
            company=CompanyPayload(
                name="OpenAI",
                domain="openai.com",
                description="OpenAI builds AI systems.",
                products=["ChatGPT"],
            ),
            confidence=0.8,
            sources=[
                SourceEvidence(
                    url="https://openai.com",
                    title="OpenAI",
                    evidence="OpenAI builds AI systems.",
                )
            ],
        )

    async def fake_lookup_wikipedia_company(_data):
        return WikipediaCompanyOutput(
            title="OpenAI",
            url="https://en.wikipedia.org/wiki/OpenAI",
            summary="OpenAI is an AI company.",
            confidence=0.8,
        )

    async def fake_get_company_provider_results(_company):
        return {
            "company_key": "openai",
            "providers": {
                "old_provider": {
                    "cached_at": "2026-04-28T00:00:00+00:00",
                    "expires_at": "2026-04-29T00:00:00+00:00",
                    "ttl_seconds": 86400,
                    "request": {"company": "OpenAI"},
                    "result": {"large": "payload"},
                },
                "company_overview": {
                    "cached_at": "2026-04-28T00:00:00+00:00",
                    "expires_at": "2026-04-29T00:00:00+00:00",
                    "ttl_seconds": 86400,
                    "request": {"company": "OpenAI"},
                    "result": {"recursive": True},
                },
            },
        }

    async def fake_upsert_company_provider_result(**kwargs):
        calls["upsert"] = kwargs
        return True

    class FakeOpenRouterClient:
        async def synthesize_json(self, prompt: str):
            calls["prompt"] = prompt
            return {
                "summary": "OpenAI is an AI company with notable products and recent news.",
                "what_they_do": ["Builds AI systems."],
                "market_position": ["Major AI lab and product company."],
                "products": ["ChatGPT"],
                "recent_developments": ["OpenAI launched a product."],
                "interview_angles": ["Discuss product direction."],
                "uncertainties": [],
            }

    monkeypatch.setattr(company_overview, "fetch_recent_news", fake_fetch_recent_news)
    monkeypatch.setattr(company_overview, "lookup_linkedin_company", fake_lookup_linkedin_company)
    monkeypatch.setattr(company_overview, "build_company_profile", fake_build_company_profile)
    monkeypatch.setattr(company_overview, "lookup_wikipedia_company", fake_lookup_wikipedia_company)
    monkeypatch.setattr(company_overview, "get_company_provider_results", fake_get_company_provider_results)
    monkeypatch.setattr(
        company_overview,
        "upsert_company_provider_result",
        fake_upsert_company_provider_result,
    )
    monkeypatch.setattr(company_overview, "OpenRouterClient", FakeOpenRouterClient)

    result = await company_overview.build_company_overview(
        CompanyOverviewInput(company="OpenAI", domain="openai.com")
    )

    assert result.task == "company_overview"
    assert result.synthesis_task == "final_brief"
    assert result.company.name == "OpenAI"
    assert result.overview.what_they_do == "Builds AI systems."
    assert result.overview.market_position == "Major AI lab and product company."
    assert result.overview.products == ["ChatGPT"]
    assert "Provider data" in calls["prompt"]
    assert calls["upsert"]["provider"] == "company_overview"
    assert "cached_company_results" not in calls["upsert"]["result"]["providers"]
    assert "result" not in result.providers["cached_company_results"]["providers"]["old_provider"]
    assert "company_overview" not in result.providers["cached_company_results"]["providers"]
    assert result.providers["wikipedia_company"]["title"] == "OpenAI"


@pytest.mark.anyio
async def test_company_overview_falls_back_without_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_recent_news(_data):
        return RecentNewsOutput(items=[], query_used="q", confidence=0.0)

    async def fake_lookup_linkedin_company(_data):
        return LinkedInCompanyLookupOutput(matches=[], query_used="q", confidence=0.0)

    async def fake_get_company_provider_results(_company):
        return None

    async def fake_purge_company_provider_results(_company, _domain=None):
        return {
            "company_key": "openai",
            "deleted_keys": ["company_research:v1:openai"],
            "deleted_count": 1,
        }

    async def fake_upsert_company_provider_result(**_kwargs):
        return True

    class FakeOpenRouterClient:
        async def synthesize_json(self, _prompt: str):
            raise company_overview.OpenRouterUnavailable("OPENROUTER_API_KEY is not configured.")

    monkeypatch.setattr(company_overview, "fetch_recent_news", fake_fetch_recent_news)
    monkeypatch.setattr(company_overview, "lookup_linkedin_company", fake_lookup_linkedin_company)
    monkeypatch.setattr(company_overview, "get_company_provider_results", fake_get_company_provider_results)
    monkeypatch.setattr(
        company_overview,
        "purge_company_provider_results",
        fake_purge_company_provider_results,
    )
    monkeypatch.setattr(
        company_overview,
        "upsert_company_provider_result",
        fake_upsert_company_provider_result,
    )
    monkeypatch.setattr(company_overview, "OpenRouterClient", FakeOpenRouterClient)

    result = await company_overview.build_company_overview(
        CompanyOverviewInput(company="OpenAI", include_wikipedia=False)
    )

    assert result.overview.summary
    assert "OPENROUTER_API_KEY is not configured." in result.warnings


@pytest.mark.anyio
async def test_company_overview_skips_openrouter_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_recent_news(data):
        assert data.use_openrouter is False
        return RecentNewsOutput(
            items=[
                RecentNewsItem(
                    title="OpenAI launches a product",
                    url="https://example.com/news",
                    summary="OpenAI launched a product.",
                )
            ],
            query_used="q",
            confidence=0.7,
        )

    async def fake_lookup_linkedin_company(data):
        assert data.use_openrouter is False
        return LinkedInCompanyLookupOutput(matches=[], query_used="q", confidence=0.0)

    async def fake_build_company_profile(data):
        assert data.use_openrouter is False
        return CompanyProfileOutput(
            company=CompanyPayload(
                name="OpenAI",
                domain="openai.com",
                description="OpenAI builds AI systems.",
            ),
            confidence=0.7,
        )

    async def fake_get_company_provider_results(_company):
        return None

    async def fake_upsert_company_provider_result(**_kwargs):
        return True

    class FakeOpenRouterClient:
        async def synthesize_json(self, _prompt: str):
            raise AssertionError("OpenRouter should not be called when use_openrouter is false")

    monkeypatch.setattr(company_overview, "fetch_recent_news", fake_fetch_recent_news)
    monkeypatch.setattr(company_overview, "lookup_linkedin_company", fake_lookup_linkedin_company)
    monkeypatch.setattr(company_overview, "build_company_profile", fake_build_company_profile)
    monkeypatch.setattr(company_overview, "get_company_provider_results", fake_get_company_provider_results)
    monkeypatch.setattr(
        company_overview,
        "upsert_company_provider_result",
        fake_upsert_company_provider_result,
    )
    monkeypatch.setattr(company_overview, "OpenRouterClient", FakeOpenRouterClient)

    result = await company_overview.build_company_overview(
        CompanyOverviewInput(
            company="OpenAI",
            domain="openai.com",
            include_wikipedia=False,
            use_openrouter=False,
        )
    )

    assert result.overview.summary == "OpenAI builds AI systems."
    assert "OpenRouter final brief synthesis skipped because use_openrouter is false." in result.warnings


@pytest.mark.anyio
async def test_company_overview_force_refresh_purges_company_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    async def fake_fetch_recent_news(_data):
        return RecentNewsOutput(items=[], query_used="q", confidence=0.0)

    async def fake_lookup_linkedin_company(_data):
        return LinkedInCompanyLookupOutput(matches=[], query_used="q", confidence=0.0)

    async def fake_get_company_provider_results(_company):
        return None

    async def fake_purge_company_provider_results(company, domain=None):
        calls["purged"] = company
        calls["domain"] = domain
        return {
            "company_key": "openai",
            "deleted_keys": ["company_research:v1:openai"],
            "deleted_count": 1,
        }

    async def fake_upsert_company_provider_result(**_kwargs):
        return True

    class FakeOpenRouterClient:
        async def synthesize_json(self, _prompt: str):
            return {
                "summary": "Clean overview.",
                "what_they_do": "Builds AI systems.",
                "market_position": None,
                "products": [],
                "recent_developments": [],
                "interview_angles": [],
                "uncertainties": [],
            }

    monkeypatch.setattr(company_overview, "fetch_recent_news", fake_fetch_recent_news)
    monkeypatch.setattr(company_overview, "lookup_linkedin_company", fake_lookup_linkedin_company)
    monkeypatch.setattr(company_overview, "get_company_provider_results", fake_get_company_provider_results)
    monkeypatch.setattr(
        company_overview,
        "purge_company_provider_results",
        fake_purge_company_provider_results,
    )
    monkeypatch.setattr(
        company_overview,
        "upsert_company_provider_result",
        fake_upsert_company_provider_result,
    )
    monkeypatch.setattr(company_overview, "OpenRouterClient", FakeOpenRouterClient)

    result = await company_overview.build_company_overview(
        CompanyOverviewInput(company="OpenAI", include_wikipedia=False, force_refresh=True)
    )

    assert calls["purged"] == "OpenAI"
    assert calls["domain"] is None
    assert result.providers["cache_purge"]["deleted_count"] == 1
    assert "Purged cached company results for OpenAI." in result.warnings
