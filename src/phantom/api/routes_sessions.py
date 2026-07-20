"""Persistent session REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from phantom.api.auth import verify_token_dep
from phantom.services.session_service import SessionConflict, SessionNotFound

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token_dep)])


class StartSessionRequest(BaseModel):
    idempotency_key: str | None = None


class StopSessionRequest(BaseModel):
    idempotency_key: str | None = None


def _service(request: Request):
    return request.app.state.session_service


@router.post("/profiles/{profile_id}/sessions", status_code=status.HTTP_201_CREATED)
def start_session(profile_id: int, request: Request, body: StartSessionRequest | None = None,
                  idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                  response: Response = None):
    key = idempotency_key or (body.idempotency_key if body else None)
    try:
        session, created = _service(request).start(profile_id, key)
    except SessionNotFound:
        raise HTTPException(404, "profile not found")
    except SessionConflict as exc:
        raise HTTPException(409, str(exc))
    if response is not None and not created:
        response.status_code = 200
    return session


@router.get("/sessions")
def list_sessions(request: Request):
    sessions = _service(request).list()
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request):
    try:
        return _service(request).get(session_id)
    except SessionNotFound:
        raise HTTPException(404, "session not found")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_202_ACCEPTED)
def stop_session(session_id: str, request: Request, body: StopSessionRequest | None = None,
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                 response: Response = None):
    key = idempotency_key or (body.idempotency_key if body else None)
    try:
        session, changed = _service(request).stop(session_id, key)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except SessionConflict as exc:
        raise HTTPException(409, str(exc))
    if response is not None and not changed:
        response.status_code = 200
    return session
