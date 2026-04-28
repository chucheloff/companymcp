import json
import re

from pydantic import ValidationError

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
        if isinstance(raw, list):
            raw = next((item for item in raw if isinstance(item, dict)), {})
        if isinstance(raw, dict):
            raw = _coerce_extracted_facts(raw)
        try:
            return ExtractedFacts.model_validate(raw)
        except ValidationError as exc:
            return ExtractedFacts(
                confidence=0.0,
                warnings=[f"OpenRouter extraction returned invalid facts: {exc}"],
            )


def get_pipeline() -> ExtractorPipeline:
    return LlmExtractPipeline()


def _coerce_extracted_facts(raw: dict) -> dict:
    payload = dict(raw)
    confidence = payload.get("confidence")
    if isinstance(confidence, str):
        match = re.search(r"0(?:\.\d+)?|1(?:\.0+)?", confidence)
        if match:
            payload["confidence"] = float(match.group(0))
    for key in ["products", "evidence", "warnings"]:
        value = payload.get(key)
        if value is None:
            payload[key] = []
        elif isinstance(value, str):
            payload[key] = [value]
    return payload
