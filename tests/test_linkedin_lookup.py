import pytest

from company_mcp.mcp.schemas import LinkedInLookupInput, LinkedInLookupOutput, LinkedInMatch
from company_mcp.providers.linkedin_lookup import (
    _cache_key,
    _is_public_linkedin_profile,
    _score_match,
    _ttl_seconds,
    lookup_linkedin,
)


@pytest.mark.anyio
async def test_linkedin_lookup_ranks_public_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(_key: str):
        return None

    async def fake_set_json(_key: str, _value: dict, ttl_seconds: int):
        return True

    async def fake_tavily_search(**_kwargs):
        return {
            "results": [
                {
                    "title": "Jane Doe - Engineering Manager - Example",
                    "url": "https://www.linkedin.com/in/jane-doe",
                    "content": "Jane Doe is an Engineering Manager at Example.",
                },
                {
                    "title": "Jane Doe profiles",
                    "url": "https://www.linkedin.com/pub/dir/jane/doe",
                    "content": "Directory page",
                },
            ]
        }

    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.get_json", fake_get_json)
    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.set_json", fake_set_json)
    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.settings.tavily_api_key", "test-key")
    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.settings.openrouter_api_key", None)
    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.tavily_search", fake_tavily_search)

    result = await lookup_linkedin(
        LinkedInLookupInput(name="Jane Doe", company="Example", title_hint="Engineering Manager")
    )

    assert len(result.matches) == 1
    assert result.matches[0].company_match is True
    assert result.matches[0].confidence >= 0.8


def test_linkedin_lookup_caps_company_only_match() -> None:
    confidence, evidence, company_match = _score_match(
        LinkedInLookupInput(name="Sam Altman", company="OpenAI", title_hint="CEO"),
        title="Larry James Erwin - OpenAI",
        content="Larry works at OpenAI.",
        url="https://www.linkedin.com/in/iamlarryjames",
        normalized={},
    )

    assert company_match is True
    assert confidence <= 0.4
    assert "requested name not confirmed" in evidence


def test_linkedin_lookup_penalizes_normalized_mismatch() -> None:
    confidence, evidence, company_match = _score_match(
        LinkedInLookupInput(name="Sam Altman", company="OpenAI", title_hint="CEO"),
        title="Sam Altman",
        content="Sam Altman profile",
        url="https://www.linkedin.com/in/sam-altman-4384094",
        normalized={
            "name": "Sam Altman",
            "title": "President",
            "current_company": "Altman Technologies, Inc.",
            "headline": "President at Altman Technologies, Inc.",
        },
    )

    assert company_match is False
    assert confidence < 0.6
    assert "normalized company did not match requested company" in evidence
    assert "normalized title did not match title hint" in evidence


def test_linkedin_lookup_uses_short_ttl_for_weak_results() -> None:
    assert _ttl_seconds(LinkedInLookupOutput(matches=[], query_used="q")) == 3600
    assert (
        _ttl_seconds(
            LinkedInLookupOutput(
                matches=[LinkedInMatch(name="A", url="https://www.linkedin.com/in/a", confidence=0.4)],
                query_used="q",
                confidence=0.4,
            )
        )
        == 3600
    )
    assert (
        _ttl_seconds(
            LinkedInLookupOutput(
                matches=[LinkedInMatch(name="A", url="https://www.linkedin.com/in/a", confidence=0.6)],
                query_used="q",
                confidence=0.6,
            )
        )
        == 24 * 3600
    )


def test_linkedin_lookup_rejects_spoofed_linkedin_hostname() -> None:
    assert _is_public_linkedin_profile("https://www.linkedin.com/in/jane-doe") is True
    assert _is_public_linkedin_profile("https://evil-linkedin.com/in/jane-doe") is False


def test_linkedin_lookup_cache_key_is_purgeable_by_company() -> None:
    key = _cache_key(
        LinkedInLookupInput(name="Jane Doe", company="Example Inc"),
        '"Jane Doe" site:linkedin.com/in "Example Inc"',
    )

    assert key.startswith("linkedin_lookup:v3:jane-doe:example-inc:")
