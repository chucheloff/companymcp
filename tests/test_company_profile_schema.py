from company_mcp.mcp.schemas import CompanyProfileInput


def test_company_profile_defaults() -> None:
    payload = CompanyProfileInput(domain="example.com")
    assert payload.max_pages == 8
    assert payload.freshness_hours == 168
