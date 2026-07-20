"""Proxy CRUD + health REST endpoints — /v1/proxies."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from phantom.api.auth import verify_token_dep
from phantom.api.models import (
    ProxyCreate,
    ProxyHealthResponse,
    ProxyListResponse,
    ProxyResponse,
    ProxyUpdate,
)
from phantom.services import proxy_service

router = APIRouter(
    prefix="/v1/proxies",
    tags=["proxies"],
    dependencies=[Depends(verify_token_dep)],
)


@router.get("", response_model=ProxyListResponse)
async def list_proxies() -> ProxyListResponse:
    """List all proxies (passwords redacted)."""
    rows = proxy_service.list_proxies()
    proxies = [ProxyResponse(**r) for r in rows]
    return ProxyListResponse(proxies=proxies, count=len(proxies))


@router.post("", response_model=ProxyResponse, status_code=HTTP_201_CREATED)
async def create_proxy(body: ProxyCreate) -> ProxyResponse:
    """Create a new proxy entry."""
    try:
        result = proxy_service.create_proxy(
            name=body.name,
            scheme=body.scheme,
            host=body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    return ProxyResponse(**result)


@router.get("/{proxy_id}", response_model=ProxyResponse)
async def get_proxy(proxy_id: int) -> ProxyResponse:
    """Get a single proxy by ID (password redacted)."""
    row = proxy_service.get_proxy(proxy_id)
    if row is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    return ProxyResponse(**row)


@router.put("/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(proxy_id: int, body: ProxyUpdate) -> ProxyResponse:
    """Update an existing proxy."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    try:
        result = proxy_service.update_proxy(proxy_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    if result is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )
    return ProxyResponse(**result)


@router.delete("/{proxy_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_proxy(proxy_id: int) -> None:
    """Delete a proxy.  Refuses if any profile references it."""
    try:
        ok = proxy_service.delete_proxy(proxy_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    if not ok:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Proxy {proxy_id} not found",
        )


@router.post("/{proxy_id}/check", response_model=ProxyHealthResponse)
async def check_proxy_health(proxy_id: int) -> ProxyHealthResponse:
    """Run a structured health check on a proxy.

    Checks connectivity and returns latency + exit IP.
    Updates the proxy's ``health_status`` in the DB.
    Does NOT log or return credentials.
    """
    try:
        result = proxy_service.check_proxy_health(proxy_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return ProxyHealthResponse(**result)
