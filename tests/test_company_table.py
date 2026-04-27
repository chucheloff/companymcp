from datetime import UTC, datetime, timedelta

import pytest

from company_mcp.cache import company_table


@pytest.mark.anyio
async def test_upsert_company_provider_result_prunes_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(UTC)
    writes = {}

    async def fake_get_json(_key: str):
        return {
            "company_key": "openai",
            "providers": {
                "old": {
                    "expires_at": (now - timedelta(seconds=5)).isoformat(),
                    "result": {"stale": True},
                }
            },
        }

    async def fake_set_json(key: str, value: dict, ttl_seconds: int):
        writes["key"] = key
        writes["value"] = value
        writes["ttl_seconds"] = ttl_seconds
        return True

    monkeypatch.setattr(company_table, "get_json", fake_get_json)
    monkeypatch.setattr(company_table, "set_json", fake_set_json)

    result = await company_table.upsert_company_provider_result(
        company="OpenAI",
        provider="recent_news",
        result={"items": []},
        ttl_seconds=3600,
        request={"company": "OpenAI"},
    )

    assert result is True
    assert writes["key"] == "company_research:v1:openai"
    assert "old" not in writes["value"]["providers"]
    assert writes["value"]["providers"]["recent_news"]["result"] == {"items": []}
