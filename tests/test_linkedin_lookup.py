import pytest

from company_mcp.mcp.schemas import LinkedInLookupInput
from company_mcp.providers.linkedin_lookup import lookup_linkedin


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
    monkeypatch.setattr("company_mcp.providers.linkedin_lookup.tavily_search", fake_tavily_search)

    result = await lookup_linkedin(
        LinkedInLookupInput(name="Jane Doe", company="Example", title_hint="Engineering Manager")
    )

    assert len(result.matches) == 1
    assert result.matches[0].company_match is True
    assert result.matches[0].confidence >= 0.8
