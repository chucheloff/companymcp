import json

from company_mcp.extractors.base import ExtractedFacts, ExtractorPipeline, PageDocument
from company_mcp.models.openrouter import OpenRouterClient, OpenRouterUnavailable


class LlmExtractPipeline:
    name = "llm_extract"

    def __init__(self, client: OpenRouterClient | None = None) -> None:
        self.client = client or OpenRouterClient()

    async def extract(self, pages: list[PageDocument]) -> ExtractedFacts:
        source_text = "\n\n".join(
            f"URL: {page.url}\nTITLE: {page.title}\nTEXT: {page.text[:2500]}" for page in pages[:5]
        )
        prompt = (
            "Extract company profile facts from these public pages. "
            "Return JSON with keys: name, description, industry, products, hq, size, "
            "careers_url, linkedin_url, confidence, evidence, warnings.\n\n"
            f"{source_text}"
        )
        try:
            raw = await self.client.extract_json(prompt)
        except OpenRouterUnavailable as exc:
            return ExtractedFacts(confidence=0.0, warnings=[str(exc)])
        except Exception as exc:
            return ExtractedFacts(confidence=0.0, warnings=[f"OpenRouter extraction failed: {exc}"])

        if isinstance(raw, str):
            raw = json.loads(raw)
        return ExtractedFacts.model_validate(raw)


def get_pipeline() -> ExtractorPipeline:
    return LlmExtractPipeline()
