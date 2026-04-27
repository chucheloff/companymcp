import json

from fastapi.testclient import TestClient

from company_mcp.app import app


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
