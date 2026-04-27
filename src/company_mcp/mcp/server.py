from fastmcp import FastMCP

from company_mcp.mcp.schemas import CompanyProfileInput, LinkedInLookupInput, RecentNewsInput
from company_mcp.providers.company_profile import build_company_profile
from company_mcp.providers.linkedin_lookup import lookup_linkedin
from company_mcp.providers.tavily_news import fetch_recent_news

mcp = FastMCP("company-research")


@mcp.tool()
async def company_profile(
    domain: str,
    max_pages: int = 8,
    freshness_hours: int = 168,
    pipeline: str = "auto",
) -> dict:
    """Return a structured company profile with source evidence."""
    payload = CompanyProfileInput(
        domain=domain,
        max_pages=max_pages,
        freshness_hours=freshness_hours,
        pipeline=pipeline,
    )
    result = await build_company_profile(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def recent_news(company: str, days: int = 30, domain: str | None = None, limit: int = 8) -> dict:
    """Return recent company news from Tavily."""
    payload = RecentNewsInput(company=company, domain=domain, days=days, limit=limit)
    result = await fetch_recent_news(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def linkedin_lookup(
    name: str,
    company: str | None = None,
    title_hint: str | None = None,
    limit: int = 5,
) -> dict:
    """Return ranked public LinkedIn profile candidates from search snippets."""
    payload = LinkedInLookupInput(
        name=name,
        company=company,
        title_hint=title_hint,
        limit=limit,
    )
    result = await lookup_linkedin(payload)
    return result.model_dump(mode="json")
