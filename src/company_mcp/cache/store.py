import json
from typing import Any

from redis.asyncio import Redis, from_url

from company_mcp.config import settings

_redis_client: Redis | None = None
_connection_attempted = False


async def _get_client() -> Redis | None:
    global _redis_client, _connection_attempted
    if _redis_client is not None:
        return _redis_client
    if _connection_attempted:
        return None

    _connection_attempted = True
    try:
        client = from_url(settings.valkey_url, decode_responses=True)
        await client.ping()
        _redis_client = client
    except Exception:
        _redis_client = None
    return _redis_client


async def get_json(key: str) -> dict[str, Any] | None:
    client = await _get_client()
    if client is None:
        return None
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def set_json(key: str, value: dict[str, Any], ttl_seconds: int) -> bool:
    client = await _get_client()
    if client is None:
        return False
    await client.set(key, json.dumps(value), ex=ttl_seconds)
    return True
