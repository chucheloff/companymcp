import pytest

from company_mcp.extractors.base import PageDocument
from company_mcp.extractors.llm_extract import LlmExtractPipeline
from company_mcp.extractors.registry import merge_facts, run_extractors


@pytest.mark.anyio
async def test_metadata_pipeline_extracts_org_json_ld() -> None:
    html = """
    <html>
      <head>
        <title>Acme</title>
        <meta property="og:description" content="Acme builds interview tools.">
        <script type="application/ld+json">
        {
          "@type": "Organization",
          "name": "Acme Research",
          "sameAs": ["https://www.linkedin.com/company/acme-research"]
        }
        </script>
      </head>
      <body><a href="/careers">Careers</a></body>
    </html>
    """
    pages = [PageDocument(url="https://acme.example", title="Acme", html=html)]

    facts = merge_facts(await run_extractors(pages, "metadata"))

    assert facts.name == "Acme Research"
    assert facts.description == "Acme builds interview tools."
    assert facts.linkedin_url == "https://www.linkedin.com/company/acme-research"
    assert facts.careers_url == "https://acme.example/careers"
    assert facts.confidence > 0.4


@pytest.mark.anyio
async def test_llm_pipeline_accepts_list_wrapped_facts() -> None:
    class FakeClient:
        async def extract_json(self, _prompt: str):
            return [
                {
                    "name": "Acme",
                    "description": "Acme builds tools.",
                    "confidence": "0.70, based on limited evidence",
                    "evidence": "homepage text",
                }
            ]

    facts = await LlmExtractPipeline(client=FakeClient()).extract(
        [PageDocument(url="https://acme.example", title="Acme", html="", text="Acme builds tools.")]
    )

    assert facts.name == "Acme"
    assert facts.description == "Acme builds tools."
    assert facts.confidence == 0.7
    assert facts.evidence == ["homepage text"]
