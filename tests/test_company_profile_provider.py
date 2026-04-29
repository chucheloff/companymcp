import pytest

from company_mcp.mcp.schemas import CompanyProfileInput
from company_mcp.providers.company_profile import (
    _company_profile_cache_key,
    _extract_meta_description,
    _extract_title,
    _fetch_public_url,
    _is_probably_challenge_page,
    _is_safe_public_domain,
    _normalize_domain,
    build_company_profile,
)
from company_mcp.extractors.base import PageDocument


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


def test_company_profile_cache_key_includes_page_limit() -> None:
    first = _company_profile_cache_key(
        CompanyProfileInput(domain="example.com", max_pages=2),
        "example.com",
    )
    second = _company_profile_cache_key(
        CompanyProfileInput(domain="example.com", max_pages=8),
        "example.com",
    )

    assert first != second


def test_company_profile_cache_key_includes_freshness() -> None:
    first = _company_profile_cache_key(
        CompanyProfileInput(domain="example.com", freshness_hours=1),
        "example.com",
    )
    second = _company_profile_cache_key(
        CompanyProfileInput(domain="example.com", freshness_hours=168),
        "example.com",
    )

    assert first != second


def test_challenge_page_detection() -> None:
    page = PageDocument(
        url="https://openai.com",
        title="Just a moment...",
        html="",
        text="Verification successful. Waiting for openai.com to respond",
    )

    assert _is_probably_challenge_page(page) is True


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
        is_redirect = False
        headers = {}
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

    result = await build_company_profile(
        CompanyProfileInput(domain="example.com", max_pages=2, pipeline="metadata")
    )
    assert len(result.sources) >= 2
    assert calls["get"] == 2
    assert calls["set"] == 1


@pytest.mark.anyio
async def test_fetch_public_url_blocks_private_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    class RedirectResponse:
        status_code = 302
        is_redirect = True
        headers = {"location": "https://127.0.0.1/admin"}
        text = ""
        url = "https://example.com"

    class FakeClient:
        async def get(self, *_args, **_kwargs):
            return RedirectResponse()

    monkeypatch.setattr(
        "company_mcp.providers.company_profile._is_safe_public_domain",
        lambda domain: domain == "example.com",
    )

    with pytest.raises(ValueError, match="target host"):
        await _fetch_public_url(FakeClient(), "https://example.com")
