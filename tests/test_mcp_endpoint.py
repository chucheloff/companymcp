import json

import pytest
from fastapi.testclient import TestClient

from company_mcp.app import app
from company_mcp.mcp import server
from company_mcp.mcp.schemas import (
    CompanyPayload,
    CompanyProfileOutput,
    LinkedInCompanyLookupOutput,
    RecentNewsOutput,
    WikipediaCompanyOutput,
)


def _extract_sse_json(response_text: str) -> dict:
    for line in response_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: ").strip())
    raise AssertionError(f"No SSE data payload found in response: {response_text!r}")


def test_mcp_company_profile_tool_call() -> None:
    with TestClient(app) as client:
        mcp_headers = {"Accept": "application/json, text/event-stream"}
        init_response = client.post(
            "/mcp",
            headers=mcp_headers,
            json={
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1.0"},
                },
            },
        )
        assert init_response.status_code == 200
        init_json = _extract_sse_json(init_response.text)
        assert "result" in init_json

        session_id = init_response.headers.get("mcp-session-id")
        headers = dict(mcp_headers)
        if session_id:
            headers["mcp-session-id"] = session_id

        # Some MCP servers expect an initialized notification before tool calls.
        client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

        tool_response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": "tool-1",
                "method": "tools/call",
                "params": {
                    "name": "company_profile",
                    "arguments": {"domain": "example.com", "max_pages": 2},
                },
            },
        )
        assert tool_response.status_code == 200
        body = _extract_sse_json(tool_response.text)
        assert "result" in body


@pytest.mark.anyio
async def test_mcp_tools_pass_force_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    async def fake_build_company_profile(payload):
        calls["company_profile"] = payload.force_refresh
        return CompanyProfileOutput(
            company=CompanyPayload(name="Example", domain="example.com"),
            confidence=0.1,
        )

    async def fake_fetch_recent_news(payload):
        calls["recent_news"] = payload.force_refresh
        return RecentNewsOutput(items=[], query_used="q", confidence=0.0)

    async def fake_lookup_linkedin_company(payload):
        calls["linkedin_company_lookup"] = payload.force_refresh
        return LinkedInCompanyLookupOutput(matches=[], query_used="q", confidence=0.0)

    async def fake_lookup_wikipedia_company(payload):
        calls["wikipedia_company"] = payload.force_refresh
        return WikipediaCompanyOutput(confidence=0.0)

    monkeypatch.setattr(server, "build_company_profile", fake_build_company_profile)
    monkeypatch.setattr(server, "fetch_recent_news", fake_fetch_recent_news)
    monkeypatch.setattr(server, "lookup_linkedin_company", fake_lookup_linkedin_company)
    monkeypatch.setattr(server, "lookup_wikipedia_company", fake_lookup_wikipedia_company)

    await server.company_profile("example.com", force_refresh=True)
    await server.recent_news("Example", force_refresh=True)
    await server.linkedin_company_lookup("Example", force_refresh=True)
    await server.wikipedia_company("Example", force_refresh=True)

    assert calls == {
        "company_profile": True,
        "recent_news": True,
        "linkedin_company_lookup": True,
        "wikipedia_company": True,
    }
