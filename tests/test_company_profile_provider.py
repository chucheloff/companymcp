import pytest

from company_mcp.mcp.schemas import CompanyProfileInput
from company_mcp.providers.company_profile import (
    _extract_meta_description,
    _extract_title,
    _is_safe_public_domain,
    _normalize_domain,
    build_company_profile,
)


def test_normalize_domain_from_url() -> None:
    assert _normalize_domain("https://example.com/path") == "example.com"


def test_extract_title_and_description() -> None:
    html = """
    <html>
      <head>
        <title> Example Inc </title>
        <meta name="description" content="We build tools.">
      </head>
    </html>
    """
    assert _extract_title(html) == "Example Inc"
    assert _extract_meta_description(html) == "We build tools."


def test_ssrf_domain_policy_blocks_localhost() -> None:
    assert _is_safe_public_domain("localhost") is False
    assert _is_safe_public_domain("127.0.0.1") is False


@pytest.mark.anyio
async def test_company_profile_cache_hit_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(_key: str):
        return {
            "company": {
                "name": "Example",
                "domain": "example.com",
                "description": "Cached",
                "products": [],
            },
            "confidence": 0.9,
            "sources": [],
            "warnings": [],
        }

    async def fake_set_json(_key: str, _value: dict, ttl_seconds: int):
        return True

    async def fail_get(*_args, **_kwargs):
        raise AssertionError("Network should not be called on cache hit")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        get = fail_get

    monkeypatch.setattr("company_mcp.providers.company_profile.get_json", fake_get_json)
    monkeypatch.setattr("company_mcp.providers.company_profile.set_json", fake_set_json)
    monkeypatch.setattr("company_mcp.providers.company_profile._is_safe_public_domain", lambda _d: True)
    monkeypatch.setattr("company_mcp.providers.company_profile.httpx.AsyncClient", lambda **_: FakeClient())

    result = await build_company_profile(CompanyProfileInput(domain="example.com"))
    assert result.company.description == "Cached"
    assert result.confidence == 0.9


@pytest.mark.anyio
async def test_company_profile_cache_miss_fetches_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_json(_key: str):
        return None

    calls = {"set": 0, "get": 0}

    async def fake_set_json(_key: str, _value: dict, ttl_seconds: int):
        _ = ttl_seconds
        calls["set"] += 1
        return True

    class FakeResponse:
        status_code = 200
        text = (
            "<html><head><title>Example</title>"
            '<meta name="description" content="About us"></head></html>'
        )
        url = "https://example.com/about"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            calls["get"] += 1
            return FakeResponse()

    monkeypatch.setattr("company_mcp.providers.company_profile.get_json", fake_get_json)
    monkeypatch.setattr("company_mcp.providers.company_profile.set_json", fake_set_json)
    monkeypatch.setattr("company_mcp.providers.company_profile._is_safe_public_domain", lambda _d: True)
    monkeypatch.setattr("company_mcp.providers.company_profile.httpx.AsyncClient", lambda **_: FakeClient())

    result = await build_company_profile(CompanyProfileInput(domain="example.com", max_pages=2))
    assert len(result.sources) == 2
    assert calls["get"] == 2
    assert calls["set"] == 1
