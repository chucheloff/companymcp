from fastmcp import FastMCP

from company_mcp.mcp.schemas import CompanyProfileInput, RecentNewsInput
from company_mcp.providers.company_profile import build_company_profile
from company_mcp.providers.tavily_news import fetch_recent_news

mcp = FastMCP("company-research")


@mcp.tool()
async def company_profile(domain: str, max_pages: int = 8, freshness_hours: int = 168) -> dict:
    """Return a structured company profile scaffold."""
    payload = CompanyProfileInput(
        domain=domain,
        max_pages=max_pages,
        freshness_hours=freshness_hours,
    )
    result = await build_company_profile(payload)
    return result.model_dump(mode="json")


@mcp.tool()
async def recent_news(company: str, days: int = 30, domain: str | None = None, limit: int = 8) -> dict:
    """Return recent company news from Tavily."""
    payload = RecentNewsInput(company=company, domain=domain, days=days, limit=limit)
    result = await fetch_recent_news(payload)
    return result.model_dump(mode="json")
