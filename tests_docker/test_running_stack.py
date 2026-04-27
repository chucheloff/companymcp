import json
import os

import httpx

BASE_URL = os.getenv("COMPANY_MCP_BASE_URL", "http://localhost:8080")


def _extract_sse_json(response_text: str) -> dict:
    for line in response_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: ").strip())
    raise AssertionError(f"No SSE data payload found in response: {response_text!r}")


def test_running_stack_health() -> None:
    response = httpx.get(f"{BASE_URL}/healthz", timeout=10.0)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_running_stack_company_profile_mcp_call() -> None:
    mcp_headers = {"Accept": "application/json, text/event-stream"}
    init_response = httpx.post(
        f"{BASE_URL}/mcp",
        headers=mcp_headers,
        json={
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "pytest-docker", "version": "1.0"},
            },
        },
        timeout=20.0,
    )
    assert init_response.status_code == 200
    init_json = _extract_sse_json(init_response.text)
    assert "result" in init_json

    session_id = init_response.headers.get("mcp-session-id")
    headers = dict(mcp_headers)
    if session_id:
        headers["mcp-session-id"] = session_id

    httpx.post(
        f"{BASE_URL}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        timeout=10.0,
    )

    tool_response = httpx.post(
        f"{BASE_URL}/mcp",
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
        timeout=30.0,
    )
    assert tool_response.status_code == 200
    tool_json = _extract_sse_json(tool_response.text)
    assert "result" in tool_json
