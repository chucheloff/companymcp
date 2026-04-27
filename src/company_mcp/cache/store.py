import json
import time
from typing import Any

from redis.asyncio import Redis, from_url

from company_mcp.config import settings

_valkey_client: Redis | None = None
_last_failure_at = 0.0


async def _get_client() -> Redis | None:
    global _valkey_client, _last_failure_at
    if _valkey_client is not None:
        return _valkey_client
    if _last_failure_at and time.monotonic() - _last_failure_at < settings.valkey_retry_seconds:
        return None

    try:
        client = from_url(settings.valkey_url, decode_responses=True)
        await client.ping()
        _valkey_client = client
        _last_failure_at = 0.0
    except Exception:
        _valkey_client = None
        _last_failure_at = time.monotonic()
    return _valkey_client


async def get_json(key: str) -> dict[str, Any] | None:
    global _valkey_client, _last_failure_at
    client = await _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception:
        _valkey_client = None
        _last_failure_at = time.monotonic()
        return None
    if raw is None:
        return None
    return json.loads(raw)


async def set_json(key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
    global _valkey_client, _last_failure_at
    client = await _get_client()
    if client is None:
        return False
    try:
        await client.set(key, json.dumps(value), ex=ttl_seconds)
        return True
    except Exception:
        _valkey_client = None
        _last_failure_at = time.monotonic()
        return False
