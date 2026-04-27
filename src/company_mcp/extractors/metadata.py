from company_mcp.extractors.base import ExtractedFacts, ExtractorPipeline, PageDocument
from company_mcp.extractors.html_utils import extract_json_ld, extract_links, extract_meta


class MetadataExtractor:
    name = "metadata"

    async def extract(self, pages: list[PageDocument]) -> ExtractedFacts:
        facts = ExtractedFacts()
        evidence: list[str] = []
        for page in pages:
            metadata = page.metadata or extract_meta(page.html)
            title = page.title
            description = (
                metadata.get("description")
                or metadata.get("og:description")
                or metadata.get("twitter:description")
            )
            site_name = metadata.get("og:site_name")
            if not facts.name:
                facts.name = site_name or _clean_title(title)
            if description and not facts.description:
                facts.description = description
                evidence.append(description)

            for block in extract_json_ld(page.html):
                _merge_json_ld(facts, block, evidence)

            for url, label in extract_links(page.html, page.url):
                lowered = f"{url} {label}".lower()
                if "linkedin.com/company" in lowered and not facts.linkedin_url:
                    facts.linkedin_url = url
                if any(token in lowered for token in ("careers", "jobs", "join us")):
                    if not facts.careers_url:
                        facts.careers_url = url

        signal_count = sum(
            bool(value)
            for value in [
                facts.name,
                facts.description,
                facts.industry,
                facts.careers_url,
                facts.linkedin_url,
            ]
        )
        facts.evidence = evidence[:6]
        facts.confidence = min(0.75, 0.15 + signal_count * 0.12)
        return facts


def get_pipeline() -> ExtractorPipeline:
    return MetadataExtractor()


def _clean_title(title: str) -> str | None:
    value = title.split("|", 1)[0].split(" - ", 1)[0].strip()
    return value or None


def _merge_json_ld(facts: ExtractedFacts, block: dict, evidence: list[str]) -> None:
    graph = block.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            if isinstance(item, dict):
                _merge_json_ld(facts, item, evidence)
        return

    raw_type = block.get("@type")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    if not any(t in {"Organization", "Corporation", "LocalBusiness"} for t in types):
        return

    if isinstance(block.get("name"), str):
        facts.name = block["name"]
    if not facts.description and isinstance(block.get("description"), str):
        facts.description = block["description"]
        evidence.append(block["description"])
    if not facts.linkedin_url:
        same_as = block.get("sameAs")
        candidates = same_as if isinstance(same_as, list) else [same_as]
        for candidate in candidates:
            if isinstance(candidate, str) and "linkedin.com/company" in candidate:
                facts.linkedin_url = candidate
                break
    address = block.get("address")
    if isinstance(address, dict) and not facts.hq:
        facts.hq = ", ".join(
            str(address[key])
            for key in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(key)
        ) or None
