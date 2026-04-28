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


@pytest.mark.anyio
async def test_purge_company_provider_results_deletes_company_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    async def fake_delete_keys(*keys: str):
        calls["keys"] = keys
        return len(keys)

    async def fake_delete_pattern(pattern: str):
        calls.setdefault("patterns", []).append(pattern)
        return [pattern.replace("*", "matched")]

    monkeypatch.setattr(company_table, "delete_keys", fake_delete_keys)
    monkeypatch.setattr(company_table, "delete_pattern", fake_delete_pattern)

    result = await company_table.purge_company_provider_results("OpenAI", "openai.com")

    assert calls["keys"] == ("company_research:v1:openai",)
    assert "company_profile:*:openai.com:*" in calls["patterns"]
    assert "recent_news:v2:*OpenAI*" in calls["patterns"]
    assert result["company_key"] == "openai"
    assert "company_research:v1:openai" in result["deleted_keys"]
    assert result["deleted_count"] == len(result["deleted_keys"])
