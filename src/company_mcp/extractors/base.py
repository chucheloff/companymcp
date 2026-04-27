from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field


class ExtractedFacts(BaseModel):
    name: str | None = None
    description: str | None = None
    industry: str | None = None
    products: list[str] = Field(default_factory=list)
    hq: str | None = None
    size: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PageDocument:
    url: str
    title: str
    html: str
    text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class ExtractorPipeline(Protocol):
    name: str

    async def extract(self, pages: list[PageDocument]) -> ExtractedFacts:
        ...
