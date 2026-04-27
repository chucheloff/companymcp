from company_mcp.extractors.base import ExtractedFacts, ExtractorPipeline, PageDocument
from company_mcp.extractors.dom_rules import get_pipeline as dom_rules_pipeline
from company_mcp.extractors.llm_extract import get_pipeline as llm_extract_pipeline
from company_mcp.extractors.metadata import get_pipeline as metadata_pipeline
from company_mcp.mcp.schemas import ExtractionPipelineName

EXTRACTOR_VERSION = "v2"


def selected_pipelines(name: ExtractionPipelineName) -> list[ExtractorPipeline]:
    if name == "metadata":
        return [metadata_pipeline()]
    if name == "dom_rules":
        return [dom_rules_pipeline()]
    if name == "llm_extract":
        return [llm_extract_pipeline()]
    if name == "browser_snapshot":
        return [metadata_pipeline(), dom_rules_pipeline()]
    return [metadata_pipeline(), dom_rules_pipeline(), llm_extract_pipeline()]


async def run_extractors(
    pages: list[PageDocument],
    pipeline_name: ExtractionPipelineName,
) -> list[ExtractedFacts]:
    results: list[ExtractedFacts] = []
    for pipeline in selected_pipelines(pipeline_name):
        result = await pipeline.extract(pages)
        results.append(result)
        if pipeline_name == "auto" and result.confidence >= 0.65:
            break
    return results


def merge_facts(results: list[ExtractedFacts]) -> ExtractedFacts:
    merged = ExtractedFacts()
    warnings: list[str] = []
    evidence: list[str] = []
    products: list[str] = []

    for result in sorted(results, key=lambda item: item.confidence, reverse=True):
        warnings.extend(result.warnings)
        evidence.extend(result.evidence)
        for item in result.products:
            if item not in products:
                products.append(item)
        for field in (
            "name",
            "description",
            "industry",
            "hq",
            "size",
            "careers_url",
            "linkedin_url",
        ):
            if getattr(merged, field) is None and getattr(result, field) is not None:
                setattr(merged, field, getattr(result, field))

    merged.products = products[:8]
    merged.evidence = evidence[:8]
    merged.warnings = list(dict.fromkeys(warnings))
    merged.confidence = max((result.confidence for result in results), default=0.0)
    return merged
