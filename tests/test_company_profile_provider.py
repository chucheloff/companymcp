from company_mcp.providers.company_profile import (
    _extract_meta_description,
    _extract_title,
    _normalize_domain,
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
