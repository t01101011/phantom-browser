"""Instant disposable session endpoint."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from phantom.api.auth import verify_token_dep
from phantom.services.session_service import SessionConflict, SessionNotFound
from phantom.services.lease_service import LeaseError

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token_dep)])

class InstantRequest(BaseModel):
    profile_id: int
    ttl_seconds: int = Field(default=60, ge=1, le=3600)
    idempotency_key: str | None = None

@router.post("/sessions/instant", status_code=status.HTTP_201_CREATED)
def create_instant(body: InstantRequest, request: Request, response: Response,
                   idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    key = idempotency_key or body.idempotency_key
    try:
        session, created = request.app.state.session_service.start_instant(body.profile_id, key)
        if created:
            lease = request.app.state.lease_service.acquire(session["id"], ttl_seconds=body.ttl_seconds)
        else:
            lease = None
    except SessionNotFound:
        raise HTTPException(404, "profile not found")
    except SessionConflict as exc:
        raise HTTPException(409, str(exc))
    except LeaseError as exc:
        raise HTTPException(409, str(exc))
    if not created:
        response.status_code = 200
    return {"session": session, "lease": lease}
