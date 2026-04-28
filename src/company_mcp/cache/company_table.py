from datetime import UTC, datetime, timedelta
from typing import Any

from company_mcp.cache.store import delete_keys, delete_pattern, get_json, set_json

COMPANY_TABLE_VERSION = "v1"


def company_cache_key(company: str) -> str:
    normalized = _normalize_company_key(company)
    return f"company_research:{COMPANY_TABLE_VERSION}:{normalized}"


async def upsert_company_provider_result(
    *,
    company: str | None,
    provider: str,
    result: dict[str, Any],
    ttl_seconds: int,
    request: dict[str, Any] | None = None,
) -> bool:
    if not company:
        return False

    key = company_cache_key(company)
    now = datetime.now(UTC)
    cached = await get_json(key) or {
        "company_key": _normalize_company_key(company),
        "providers": {},
    }
    providers = cached.get("providers") or {}

    pruned: dict[str, Any] = {}
    for name, entry in providers.items():
        expires_at = _parse_datetime(entry.get("expires_at"))
        if expires_at and expires_at > now:
            pruned[name] = entry

    expires_at = now + timedelta(seconds=ttl_seconds)
    pruned[provider] = {
        "cached_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl_seconds,
        "request": request or {},
        "result": result,
    }

    cached["updated_at"] = now.isoformat()
    cached["providers"] = pruned
    table_ttl = _table_ttl_seconds(pruned, now)
    return await set_json(key, cached, ttl_seconds=table_ttl)


async def get_company_provider_results(company: str) -> dict[str, Any] | None:
    return await get_json(company_cache_key(company))


async def purge_company_provider_results(company: str, domain: str | None = None) -> dict[str, Any]:
    key = company_cache_key(company)
    deleted_keys: list[str] = []
    deleted = await delete_keys(key)
    if deleted:
        deleted_keys.append(key)

    patterns = _provider_cache_patterns(company, domain)
    for pattern in patterns:
        deleted_keys.extend(await delete_pattern(pattern))

    deleted_keys = sorted(set(deleted_keys))
    return {
        "company_key": _normalize_company_key(company),
        "deleted_keys": deleted_keys,
        "deleted_count": len(deleted_keys),
    }


def _normalize_company_key(company: str) -> str:
    return "-".join(company.strip().lower().replace("_", "-").split())


def _provider_cache_patterns(company: str, domain: str | None) -> list[str]:
    company_clean = company.strip()
    company_lower = company_clean.lower()
    patterns = [
        f"recent_news:v2:*{company_clean}*",
        f"wikipedia_company:*:{company_lower}:*",
    ]
    if domain:
        domain_clean = domain.strip().lower()
        patterns.extend(
            [
                f"company_research:{COMPANY_TABLE_VERSION}:{domain_clean}",
                f"company_profile:*:{domain_clean}:*",
                f"recent_news:v2:*{domain_clean}*",
                f"wikipedia_company:*:*:{domain_clean}",
            ]
        )
    return patterns


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _table_ttl_seconds(providers: dict[str, Any], now: datetime) -> int:
    ttl = 3600
    for entry in providers.values():
        expires_at = _parse_datetime(entry.get("expires_at"))
        if expires_at:
            ttl = max(ttl, int((expires_at - now).total_seconds()))
    return max(ttl, 3600)
