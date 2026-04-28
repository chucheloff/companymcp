from fastmcp import FastMCP

from company_mcp.cache.company_table import get_company_provider_results
from company_mcp.mcp.schemas import (
    CompanyOverviewInput,
    CompanyProfileInput,
    LinkedInCompanyLookupInput,
    LinkedInLookupInput,
    RecentNewsInput,
    WikipediaCompanyInput,
)
from company_mcp.providers.company_overview import build_company_overview
from company_mcp.providers.company_profile import build_company_profile
from company_mcp.providers.linkedin_company_lookup import lookup_linkedin_company
from company_mcp.providers.linkedin_lookup import lookup_linkedin
from company_mcp.providers.tavily_news import fetch_recent_news
from company_mcp.providers.wikipedia_company import lookup_wikipedia_company

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


@mcp.tool()
async def linkedin_company_lookup(
    company: str,
    domain: str | None = None,
    limit: int = 3,
) -> dict:
    """Return ranked public LinkedIn company candidates from search snippets."""
    payload = LinkedInCompanyLookupInput(company=company, domain=domain, limit=limit)
    result = await lookup_linkedin_company(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def wikipedia_company(company: str, domain: str | None = None) -> dict:
    """Return a Wikipedia-derived company summary when a likely page exists."""
    payload = WikipediaCompanyInput(company=company, domain=domain)
    result = await lookup_wikipedia_company(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def company_overview(
    company: str,
    domain: str | None = None,
    days: int = 30,
    news_limit: int = 5,
    max_pages: int = 8,
    include_wikipedia: bool = True,
) -> dict:
    """Collect company providers and synthesize a final company overview."""
    payload = CompanyOverviewInput(
        company=company,
        domain=domain,
        days=days,
        news_limit=news_limit,
        max_pages=max_pages,
        include_wikipedia=include_wikipedia,
    )
    result = await build_company_overview(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def cached_company_results(company: str) -> dict:
    """Return company-scoped cached provider results."""
    result = await get_company_provider_results(company)
    return result or {"company_key": company, "providers": {}, "warnings": ["No cached company results found."]}
