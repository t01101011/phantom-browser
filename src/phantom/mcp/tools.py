"""MCP tools backed by the same services as the REST control plane."""
from __future__ import annotations

import base64
import json
from typing import Any

from mcp.types import CallToolResult, TextContent

from phantom.agent.actions import ActionError
from phantom.api.models import ProfileCreate, ProfileResponse
from phantom.services import profile_service
from phantom.services.lease_service import LeaseError
from phantom.services.session_service import SessionConflict, SessionNotFound


def result(data: dict[str, Any]) -> CallToolResult:
    """Return compact machine-readable output with a text compatibility view."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":"), default=str))],
        structuredContent=data,
    )


def error(code: str, message: str) -> CallToolResult:
    data = {"error": {"code": code, "message": message}}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structuredContent=data,
        isError=True,
    )


def register_tools(mcp, session_service, lease_service, action_service) -> None:
    """Register the deliberately small, truthful milestone-one tool surface."""

    @mcp.tool(description="List browser profiles. Secrets are never returned.")
    def list_profiles(platform: str | None = None) -> CallToolResult:
        rows = profile_service.list_profiles(platform_tag=platform)
        profiles = [ProfileResponse(**row).model_dump(mode="json") for row in rows]
        return result({"profiles": profiles, "count": len(profiles)})

    @mcp.tool(description="Create a persistent browser profile.")
    def create_profile(
        name: str,
        platform_tag: str = "custom",
        proxy_host: str = "",
        proxy_port: int = 0,
        proxy_user: str = "",
        proxy_pass: str = "",
        proxy_source: str = "manual",
        timezone: str | None = None,
        notes: str = "",
        folder_id: int | None = None,
        proxy_id: int | None = None,
        locale_language: str = "en",
        locale_region: str = "US",
        navigator_language: str = "en-US",
    ) -> CallToolResult:
        body = ProfileCreate(**locals())
        try:
            row = profile_service.create_profile(**body.model_dump())
        except ValueError as exc:
            return error("PROFILE_CONFLICT", str(exc))
        return result(ProfileResponse(**row).model_dump(mode="json"))

    @mcp.tool(description="Start a persistent profile session. Returns actual action capabilities; no CDP URL is advertised.")
    def start_session(profile_id: int, idempotency_key: str | None = None) -> CallToolResult:
        try:
            session, created = session_service.start(profile_id, idempotency_key)
            return result({**session, "created": created})
        except SessionNotFound:
            return error("PROFILE_NOT_FOUND", "profile not found")
        except SessionConflict as exc:
            return error("SESSION_CONFLICT", str(exc))

    @mcp.tool(description="Stop a session idempotently.")
    def stop_session(session_id: str, idempotency_key: str | None = None) -> CallToolResult:
        try:
            session, changed = session_service.stop(session_id, idempotency_key)
            return result({**session, "changed": changed})
        except SessionNotFound:
            return error("SESSION_NOT_FOUND", "session not found")
        except SessionConflict as exc:
            return error("SESSION_CONFLICT", str(exc))

    @mcp.tool(description="Acquire exclusive ownership before browser actions.")
    def acquire_lease(session_id: str, ttl_seconds: int = 60) -> CallToolResult:
        try:
            return result(lease_service.acquire(session_id, ttl_seconds=ttl_seconds))
        except SessionNotFound:
            return error("SESSION_NOT_FOUND", "session not found")
        except LeaseError as exc:
            return error("LEASE_CONFLICT", str(exc))

    def perform(session_id: str, action: str, args: dict[str, Any], lease_token: str,
                generation: int) -> CallToolResult:
        try:
            value = action_service.perform(session_id, action, args, lease_token, generation)
            if isinstance(value, bytes):
                value = {"mime": "image/png", "bytes": base64.b64encode(value).decode("ascii")}
            return result(value if isinstance(value, dict) else {"value": value})
        except SessionNotFound:
            return error("SESSION_NOT_FOUND", "session not found")
        except ActionError as exc:
            return error(exc.code, str(exc))

    @mcp.tool(description="Navigate the leased session to a URL.")
    def navigate(session_id: str, url: str, lease_token: str, generation: int) -> CallToolResult:
        return perform(session_id, "navigate", {"url": url}, lease_token, generation)

    @mcp.tool(description="Return a compact accessibility snapshot and stable generation-scoped refs.")
    def snapshot(session_id: str, lease_token: str, generation: int) -> CallToolResult:
        return perform(session_id, "snapshot", {}, lease_token, generation)

    @mcp.tool(description="Click an element ref from the current snapshot generation.")
    def click(session_id: str, ref: str, lease_token: str, generation: int) -> CallToolResult:
        return perform(session_id, "click", {"ref": ref, "generation": generation}, lease_token, generation)

    @mcp.tool(name="type", description="Type text into an element ref from the current snapshot generation.")
    def type_text(session_id: str, ref: str, text: str, lease_token: str, generation: int,
                  humanized: bool = True) -> CallToolResult:
        return perform(session_id, "type", {"ref": ref, "text": text, "generation": generation,
                                             "humanized": humanized}, lease_token, generation)

    @mcp.tool(description="Capture a PNG screenshot (base64 encoded).")
    def screenshot(session_id: str, lease_token: str, generation: int) -> CallToolResult:
        return perform(session_id, "screenshot", {}, lease_token, generation)
