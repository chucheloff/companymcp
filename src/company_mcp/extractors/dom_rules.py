from urllib.parse import urlparse

from company_mcp.extractors.base import ExtractedFacts, ExtractorPipeline, PageDocument
from company_mcp.extractors.html_utils import extract_links


class DomRulesExtractor:
    name = "dom_rules"

    async def extract(self, pages: list[PageDocument]) -> ExtractedFacts:
        facts = ExtractedFacts()
        snippets: list[str] = []
        products: set[str] = set()

        for page in pages:
            lowered_url = page.url.lower()
            text = page.text
            if text and any(marker in lowered_url for marker in ("/about", "/company")):
                snippets.append(text[:350])
            elif text and not snippets:
                snippets.append(text[:300])

            for url, label in extract_links(page.html, page.url):
                lowered = f"{url} {label}".lower()
                if "linkedin.com/company" in lowered and not facts.linkedin_url:
                    facts.linkedin_url = url
                if any(token in lowered for token in ("careers", "jobs", "join us")):
                    if not facts.careers_url:
                        facts.careers_url = url
                if any(token in lowered for token in ("product", "platform", "solutions")):
                    cleaned = label.strip()
                    if 2 <= len(cleaned) <= 80:
                        products.add(cleaned)

        if snippets:
            facts.description = " ".join(snippets)[:700]
            facts.evidence = snippets[:3]
        facts.products = sorted(products)[:8]
        facts.confidence = min(
            0.65,
            0.1
            + (0.18 if facts.description else 0)
            + (0.12 if facts.careers_url else 0)
            + (0.12 if facts.linkedin_url else 0)
            + (0.05 if facts.products else 0),
        )
        if pages and not facts.name:
            hostname = urlparse(pages[0].url).hostname or ""
            facts.name = hostname.split(".")[0].replace("-", " ").title()
        return facts


def get_pipeline() -> ExtractorPipeline:
    return DomRulesExtractor()
