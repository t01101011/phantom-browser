"""Protocol-level tests for the authenticated MCP Streamable HTTP adapter."""
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from phantom.api.app import create_app
from phantom.api.auth import load_or_generate_token


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PHANTOM_DATA_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app) as c:
        yield c


def headers(token=True, accept="application/json, text/event-stream"):
    h = {"Accept": accept, "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {load_or_generate_token()}"
    return h


def rpc(client, method, params=None, request_id=1, extra_headers=None):
    h = headers()
    if extra_headers:
        h.update(extra_headers)
    return client.post("/mcp", headers=h, json={
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}
    })


def payload(response):
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
        return json.loads(data)
    return response.json()


def initialize(client):
    r = rpc(client, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    })
    assert r.status_code == 200
    body = payload(r)
    assert body["result"]["capabilities"]["tools"] == {"listChanged": False}
    # The SDK's empty resources/prompts list handlers are real protocol
    # capabilities; Phantom advertises no unsupported browser/CDP capability.
    sid = r.headers.get("mcp-session-id")
    return sid


def test_auth_initialize_and_lifecycle(client):
    assert client.post("/mcp", headers=headers(False), json={}).status_code == 403
    assert client.post("/mcp", headers={**headers(False), "Authorization": "Bearer wrong"}, json={}).status_code == 403

    sid = initialize(client)
    h = {"Mcp-Session-Id": sid} if sid else {}
    listed = payload(rpc(client, "tools/list", extra_headers=h))
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == {"list_profiles", "create_profile", "start_session", "stop_session",
                     "acquire_lease", "navigate", "snapshot", "click", "type", "screenshot"}
    # Sessionful transports accept an explicit clean shutdown.
    if sid:
        assert client.delete("/mcp", headers={**headers(), **h}).status_code == 200


def test_call_tools_reuse_profile_semantics_and_validation(client):
    sid = initialize(client)
    h = {"Mcp-Session-Id": sid} if sid else {}
    made = payload(rpc(client, "tools/call", {"name": "create_profile", "arguments": {"name": "mcp-one"}}, extra_headers=h))
    assert made["result"]["structuredContent"]["name"] == "mcp-one"
    listed = payload(rpc(client, "tools/call", {"name": "list_profiles", "arguments": {}}, extra_headers=h))
    assert listed["result"]["structuredContent"]["count"] == 1

    invalid = payload(rpc(client, "tools/call", {"name": "create_profile", "arguments": {}}, extra_headers=h))
    assert invalid["result"]["isError"] is True
    unknown = payload(rpc(client, "tools/call", {"name": "does_not_exist", "arguments": {}}, extra_headers=h))
    assert unknown["result"]["isError"] is True


def test_domain_errors_are_compact_and_structured(client):
    sid = initialize(client)
    h = {"Mcp-Session-Id": sid} if sid else {}
    result = payload(rpc(client, "tools/call", {"name": "snapshot", "arguments": {
        "session_id": "missing", "lease_token": "x", "generation": 1}}, extra_headers=h))["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {"error": {"code": "SESSION_NOT_FOUND", "message": "session not found"}}


def test_jsonrpc_parse_and_accept_errors(client):
    bad = client.post("/mcp", headers=headers(), content="{")
    assert bad.status_code == 400
    assert payload(bad)["error"]["code"] == -32700
    unacceptable = client.post("/mcp", headers=headers(accept="application/json"), json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"}}})
    assert unacceptable.status_code == 406
