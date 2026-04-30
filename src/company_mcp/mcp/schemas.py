from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ExtractionPipelineName = Literal[
    "auto",
    "metadata",
    "dom_rules",
    "llm_extract",
    "browser_snapshot",
]


class CompanyProfileInput(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    max_pages: int = Field(default=8, ge=1, le=20)
    freshness_hours: int = Field(default=168, ge=1, le=24 * 30)
    pipeline: ExtractionPipelineName = "auto"
    use_openrouter: bool = True
    force_refresh: bool = False


class SourceEvidence(BaseModel):
    url: str
    title: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence: str


class CompanyPayload(BaseModel):
    name: str
    domain: str
    description: str | None = None
    industry: str | None = None
    products: list[str] = Field(default_factory=list)
    hq: str | None = None
    size: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None


class CompanyProfileOutput(BaseModel):
    company: CompanyPayload
    confidence: float = Field(ge=0, le=1)
    sources: list[SourceEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecentNewsInput(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    domain: str | None = None
    days: int = Field(default=30, ge=1, le=90)
    limit: int = Field(default=8, ge=1, le=20)
    use_openrouter: bool = True
    force_refresh: bool = False


class RecentNewsItem(BaseModel):
    title: str
    url: str
    published_at: str | None = None
    source: str | None = None
    summary: str | None = None
    relevance: float = Field(default=0.5, ge=0, le=1)


class RecentNewsOutput(BaseModel):
    items: list[RecentNewsItem] = Field(default_factory=list)
    query_used: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class LinkedInLookupInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    title_hint: str | None = Field(default=None, max_length=160)
    limit: int = Field(default=5, ge=1, le=10)
    use_openrouter: bool = True
    force_refresh: bool = False


class LinkedInMatch(BaseModel):
    name: str
    headline: str | None = None
    title: str | None = None
    current_company: str | None = None
    url: str
    company_match: bool = False
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class LinkedInLookupOutput(BaseModel):
    matches: list[LinkedInMatch] = Field(default_factory=list)
    query_used: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class LinkedInCompanyLookupInput(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    domain: str | None = Field(default=None, max_length=255)
    limit: int = Field(default=3, ge=1, le=10)
    use_openrouter: bool = True
    force_refresh: bool = False


class LinkedInCompanyMatch(BaseModel):
    name: str
    linkedin_url: str
    description: str | None = None
    website: str | None = None
    industry: str | None = None
    size: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class LinkedInCompanyLookupOutput(BaseModel):
    matches: list[LinkedInCompanyMatch] = Field(default_factory=list)
    query_used: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class WikipediaCompanyInput(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    domain: str | None = Field(default=None, max_length=255)
    force_refresh: bool = False


class WikipediaCompanyOutput(BaseModel):
    title: str | None = None
    url: str | None = None
    summary: str | None = None
    description: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class CompanyOverviewInput(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    domain: str | None = Field(default=None, max_length=255)
    days: int = Field(default=30, ge=1, le=90)
    news_limit: int = Field(default=5, ge=1, le=12)
    max_pages: int = Field(default=8, ge=1, le=20)
    include_wikipedia: bool = True
    use_openrouter: bool = True
    force_refresh: bool = False


class CompanyOverviewBrief(BaseModel):
    summary: str
    what_they_do: str | None = None
    market_position: str | None = None
    products: list[str] = Field(default_factory=list)
    recent_developments: list[str] = Field(default_factory=list)
    interview_angles: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CompanyOverviewOutput(BaseModel):
    task: str = "company_overview"
    synthesis_task: str = "final_brief"
    company: CompanyPayload
    overview: CompanyOverviewBrief
    providers: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceEvidence] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
