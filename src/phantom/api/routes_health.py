"""Health and readiness endpoints for Phantom Browser control plane.

* ``GET /healthz`` — Liveness probe (public, no auth required).
* ``GET /readyz`` — Readiness probe (authenticated; also checks DB).
* ``GET /v1/version`` — Version info (authenticated).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from phantom import __version__ as phantom_version
from phantom.api.auth import verify_token_dep
from phantom.api.models import HealthResponse, VersionResponse
from phantom.db import get_conn

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness probe — always returns 200 when the server is running."""
    return HealthResponse(status="ok", version=phantom_version)


@router.get(
    "/readyz",
    response_model=HealthResponse,
    dependencies=[Depends(verify_token_dep)],
)
async def readyz() -> HealthResponse:
    """Readiness probe — checks that the DB is reachable."""
    db_status = "unknown"
    try:
        with get_conn() as c:
            c.execute("SELECT 1")
            db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    return HealthResponse(status="ready", version=phantom_version, db=db_status)


@router.get(
    "/v1/version",
    response_model=VersionResponse,
    dependencies=[Depends(verify_token_dep)],
)
async def version() -> VersionResponse:
    """Return application name and version."""
    return VersionResponse()
