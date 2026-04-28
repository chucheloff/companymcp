import httpx
import pytest

from company_mcp.mcp.schemas import WikipediaCompanyInput
from company_mcp.providers import wikipedia_company


def test_wikipedia_cache_key_uses_current_provider_version() -> None:
    key = wikipedia_company._cache_key(
        WikipediaCompanyInput(company="Palantir", domain="palantir.com")
    )

    assert key == "wikipedia_company:v2:palantir:palantir.com"


def test_wikipedia_headers_include_user_agent() -> None:
    headers = wikipedia_company._headers()

    assert "User-Agent" in headers
    assert "company-mcp" in headers["User-Agent"]
    assert headers["Accept"] == "application/json"


@pytest.mark.anyio
async def test_wikipedia_summary_payload_falls_back_to_action_api() -> None:
    class FakeResponse:
        def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
            self.payload = payload or {}
            self.status_code = status_code
            self.request = httpx.Request("GET", "https://en.wikipedia.org/test")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "blocked",
                    request=self.request,
                    response=httpx.Response(self.status_code, request=self.request),
                )

        def json(self) -> dict:
            return self.payload

    class FakeClient:
        def __init__(self) -> None:
            self.urls: list[str] = []

        async def get(self, url: str, **_kwargs) -> FakeResponse:
            self.urls.append(url)
            if "rest_v1" in url:
                return FakeResponse(status_code=403)
            return FakeResponse(
                {
                    "query": {
                        "pages": [
                            {
                                "title": "Palantir Technologies",
                                "extract": "Palantir Technologies is a software company.",
                                "fullurl": "https://en.wikipedia.org/wiki/Palantir_Technologies",
                                "pageprops": {"wikibase-shortdesc": "American software company"},
                            }
                        ]
                    }
                }
            )

    payload = await wikipedia_company._summary_payload(FakeClient(), "Palantir Technologies")

    assert payload["title"] == "Palantir Technologies"
    assert payload["extract"] == "Palantir Technologies is a software company."
    assert payload["description"] == "American software company"
    assert payload["content_urls"]["desktop"]["page"].endswith("Palantir_Technologies")
