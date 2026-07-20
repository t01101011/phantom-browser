"""Pydantic models for Phantom Browser REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Health ─────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Response for /healthz and /readyz."""

    status: str
    version: str
    db: str | None = None


class VersionResponse(BaseModel):
    """Response for /v1/version."""

    name: str = "phantom-browser"
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    """Standard error payload."""

    detail: str


# ── Profile ────────────────────────────────────────────────────────────────────


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Unique profile name")
    platform_tag: str = Field("custom", description="facebook | tiktok | chatgpt | custom")
    proxy_host: str = Field("", description="Proxy host")
    proxy_port: int = Field(0, ge=0, le=65535, description="Proxy port")
    proxy_user: str = Field("", description="Proxy username")
    proxy_pass: str = Field("", description="Proxy password")
    proxy_source: str = Field("manual", description="manual | iproyal | file")
    timezone: Optional[str] = Field(None, description="Timezone override (e.g. America/Denver)")
    notes: str = Field("", description="Free-text notes")
    folder_id: Optional[int] = Field(None, description="Folder ID")
    proxy_id: Optional[int] = Field(None, description="Proxy ID from proxies table")
    locale_language: str = Field("en")
    locale_region: str = Field("US")
    navigator_language: str = Field("en-US")


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    platform_tag: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = Field(None, ge=0, le=65535)
    proxy_user: Optional[str] = None
    proxy_pass: Optional[str] = None
    proxy_source: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    folder_id: Optional[int] = None
    proxy_id: Optional[int] = None
    locale_language: Optional[str] = None
    locale_region: Optional[str] = None
    navigator_language: Optional[str] = None


class ProfileResponse(BaseModel):
    """Profile view returned by API — secret fields stripped."""

    id: int
    name: str
    platform_tag: str
    status: str
    target_os: str
    proxy_host: str
    proxy_port: int
    proxy_user: str
    proxy_source: str
    timezone: Optional[str] = None
    locale_language: str
    locale_region: str
    navigator_language: str
    notes: str
    folder_id: Optional[int] = None
    proxy_id: Optional[int] = None
    created_at: str
    updated_at: str


class ProfileListResponse(BaseModel):
    profiles: list[ProfileResponse]
    count: int


class ProfileCloneRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=128)


class BulkImportEntry(BaseModel):
    name: str
    platform_tag: str = "custom"
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_user: str = ""
    proxy_pass: str = ""
    timezone: Optional[str] = None
    notes: str = ""


class BulkImportRequest(BaseModel):
    profiles: list[BulkImportEntry]


# ── Folder ─────────────────────────────────────────────────────────────────────


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Unique folder name")
    parent_id: Optional[int] = Field(None, description="Parent folder ID for nesting")
    defaults_json: str = Field("{}", description="Default profile settings as JSON")


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    defaults_json: Optional[str] = None


class FolderResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    defaults_json: str
    created_at: str
    updated_at: str


class FolderListResponse(BaseModel):
    folders: list[FolderResponse]
    count: int


# ── Proxy ──────────────────────────────────────────────────────────────────────


class ProxyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Unique proxy name")
    scheme: str = Field("http", description="http | https | socks4 | socks5")
    host: str = Field(..., description="Proxy host/IP")
    port: int = Field(..., ge=1, le=65535, description="Proxy port")
    username: str = Field("", description="Proxy authentication username")
    password: str = Field("", description="Proxy authentication password")
    source: str = Field("manual", description="manual | iproyal | file")


class ProxyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    scheme: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    source: Optional[str] = None


class ProxyResponse(BaseModel):
    """Proxy view — password always redacted."""

    id: int
    name: str
    scheme: str
    host: str
    port: int
    username: str
    password: str  # Always "*****" in API responses
    source: str
    health_status: str
    last_checked_at: Optional[str] = None
    created_at: str
    updated_at: str


class ProxyListResponse(BaseModel):
    proxies: list[ProxyResponse]
    count: int


class ProxyHealthResponse(BaseModel):
    proxy_id: int
    status: str
    latency_ms: Optional[float] = None
    exit_ip: Optional[str] = None
    error: Optional[str] = None
