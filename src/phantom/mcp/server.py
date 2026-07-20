"""Authenticated MCP Streamable HTTP ASGI adapter."""
from __future__ import annotations

import secrets
from typing import Any, cast

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from phantom.api.auth import load_or_generate_token
from phantom.mcp.tools import register_tools


class BearerAuthMiddleware:
    """Apply the control-plane bearer token contract to every MCP method."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw = headers.get(b"authorization", b"").decode("latin-1")
        parts = raw.strip().split(None, 1)
        valid = (len(parts) == 2 and parts[0].lower() == "bearer" and parts[1]
                 and secrets.compare_digest(parts[1], load_or_generate_token()))
        if not valid:
            response = JSONResponse({"detail": "Invalid or missing auth token"}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def create_mcp_app(session_service, lease_service, action_service):
    """Build one stateful MCP endpoint; its lifespan owns stream sessions."""
    mcp = FastMCP(
        "Phantom Browser",
        instructions="Manage browser profiles and lease-guarded action sessions.",
        streamable_http_path="/",
        json_response=False,
        stateless_http=False,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", "testserver"]
        ),
    )
    register_tools(mcp, session_service, lease_service, action_service)
    protocol_app = mcp.streamable_http_app()
    # Expose the protocol handler directly so the canonical endpoint is exactly
    # /mcp (ASGI Mount would otherwise redirect it to /mcp/).
    handler = cast(Any, protocol_app.routes[0]).endpoint
    return BearerAuthMiddleware(handler), mcp
