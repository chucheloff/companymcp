import pytest

from company_mcp.mcp.schemas import LinkedInCompanyLookupInput, LinkedInCompanyLookupOutput
from company_mcp.providers.linkedin_company_lookup import (
    _score_company_match,
    _ttl_seconds,
    lookup_linkedin_company,
)


@pytest.mark.anyio
async def test_linkedin_company_lookup_ranks_company_page(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(_key: str):
        return None

    async def fake_set_json(_key: str, _value: dict, ttl_seconds: int):
        return True

    async def fake_upsert_company_provider_result(**_kwargs):
        return True

    async def fake_tavily_search(**_kwargs):
        return {
            "results": [
                {
                    "title": "OpenAI | LinkedIn",
                    "url": "https://www.linkedin.com/company/openai",
                    "content": "OpenAI is an AI research and deployment company. Website openai.com.",
                },
                {
                    "title": "OpenAI people",
                    "url": "https://www.linkedin.com/in/someone",
                    "content": "Not a company page.",
                },
            ]
        }

    monkeypatch.setattr("company_mcp.providers.linkedin_company_lookup.get_json", fake_get_json)
    monkeypatch.setattr("company_mcp.providers.linkedin_company_lookup.set_json", fake_set_json)
    monkeypatch.setattr(
        "company_mcp.providers.linkedin_company_lookup.upsert_company_provider_result",
        fake_upsert_company_provider_result,
    )
    monkeypatch.setattr(
        "company_mcp.providers.linkedin_company_lookup.settings.tavily_api_key",
        "test-key",
    )
    monkeypatch.setattr(
        "company_mcp.providers.linkedin_company_lookup.settings.openrouter_api_key",
        None,
    )
    monkeypatch.setattr(
        "company_mcp.providers.linkedin_company_lookup.tavily_search",
        fake_tavily_search,
    )

    result = await lookup_linkedin_company(
        LinkedInCompanyLookupInput(company="OpenAI", domain="openai.com")
    )

    assert len(result.matches) == 1
    assert result.matches[0].linkedin_url == "https://www.linkedin.com/company/openai"
    assert result.matches[0].confidence >= 0.8


def test_linkedin_company_lookup_requires_company_match_for_high_score() -> None:
    confidence, evidence = _score_company_match(
        LinkedInCompanyLookupInput(company="OpenAI", domain="openai.com"),
        title="Other Company | LinkedIn",
        content="Website openai.com.",
        url="https://www.linkedin.com/company/other",
        normalized={},
    )

    assert confidence < 0.7
    assert "requested company not confirmed" in evidence


def test_linkedin_company_lookup_uses_short_ttl_for_no_matches() -> None:
    assert _ttl_seconds(LinkedInCompanyLookupOutput(matches=[], query_used="q")) == 3600
