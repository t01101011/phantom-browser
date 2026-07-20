"""Lease ownership endpoints."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from phantom.api.auth import verify_token_dep
from phantom.services.lease_service import LeaseError
from phantom.services.session_service import SessionNotFound

router = APIRouter(prefix="/v1/sessions", dependencies=[Depends(verify_token_dep)])

class LeaseBody(BaseModel):
    ttl_seconds: int = Field(default=60, ge=1, le=3600)

class HeartbeatBody(LeaseBody):
    generation: int = Field(ge=1)

class ReleaseBody(BaseModel):
    generation: int = Field(ge=1)

class TakeoverReleaseBody(BaseModel):
    takeover_token: str = Field(min_length=20)

def owner(value: str | None = Header(None, alias="X-Lease-Token")) -> str:
    if not value:
        raise HTTPException(401, "missing lease token")
    return value

@router.post("/{session_id}/lease", status_code=201)
def acquire(session_id: str, body: LeaseBody, request: Request):
    try:
        return request.app.state.lease_service.acquire(session_id, ttl_seconds=body.ttl_seconds)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except LeaseError as exc:
        raise HTTPException(409, str(exc))

@router.post("/{session_id}/lease/heartbeat")
def heartbeat(session_id: str, body: HeartbeatBody, request: Request, token: str = Depends(owner)):
    try:
        return request.app.state.lease_service.heartbeat(session_id, token, body.generation, ttl_seconds=body.ttl_seconds)
    except SessionNotFound:
        raise HTTPException(404, "lease not found")
    except LeaseError as exc:
        raise HTTPException(409, str(exc))

@router.delete("/{session_id}/lease", status_code=204)
def release(session_id: str, body: ReleaseBody, request: Request, token: str = Depends(owner)):
    try:
        changed = request.app.state.lease_service.release(session_id, token, body.generation)
    except LeaseError as exc:
        raise HTTPException(409, str(exc))
    if not changed:
        raise HTTPException(404, "lease not found")
    return Response(status_code=204)

@router.post("/{session_id}/takeover")
def begin_takeover(session_id: str, body: ReleaseBody, request: Request, token: str = Depends(owner)):
    try:
        return request.app.state.lease_service.begin_takeover(session_id, token, body.generation)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except LeaseError as exc:
        raise HTTPException(409, str(exc))

@router.post("/{session_id}/takeover/release")
def end_takeover(session_id: str, body: TakeoverReleaseBody, request: Request):
    try:
        return request.app.state.lease_service.end_takeover(session_id, body.takeover_token)
    except LeaseError as exc:
        raise HTTPException(409, str(exc))
