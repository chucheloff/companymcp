import pytest

from company_mcp.cache import store


@pytest.mark.anyio
async def test_cache_retries_after_failure_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    store._valkey_client = None
    store._last_failure_at = 0.0
    now = {"value": 100.0}
    attempts = {"count": 0}

    class FakeClient:
        async def ping(self):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise OSError("temporary outage")
            return True

        async def get(self, _key: str):
            return None

    monkeypatch.setattr(store.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(store.settings, "valkey_retry_seconds", 5.0)
    monkeypatch.setattr(store, "from_url", lambda *_args, **_kwargs: FakeClient())

    assert await store.get_json("missing") is None
    assert attempts["count"] == 1
    assert await store.get_json("missing") is None
    assert attempts["count"] == 1

    now["value"] = 106.0
    assert await store.get_json("missing") is None
    assert attempts["count"] == 2
