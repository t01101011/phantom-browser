"""Safe artifact upload, metadata, and download endpoints."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from phantom.api.auth import verify_token_dep
from phantom.services.lease_service import ArtifactError
from phantom.services.session_service import SessionNotFound

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token_dep)])

@router.post("/sessions/{session_id}/artifacts/{artifact_type}", status_code=201)
async def upload(session_id: str, artifact_type: str, request: Request,
           content_type: str = Header(..., alias="Content-Type"),
           retention_seconds: int = 86400):
    data = await request.body()
    try:
        return request.app.state.artifact_service.put(session_id, artifact_type, content_type.split(";")[0], data,
                                                       retention_seconds=retention_seconds)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except ArtifactError as exc:
        raise HTTPException(422, str(exc))

@router.get("/sessions/{session_id}/artifacts")
def list_artifacts(session_id: str, request: Request):
    try:
        items = request.app.state.artifact_service.list(session_id)
        return {"artifacts": items, "count": len(items)}
    except SessionNotFound:
        raise HTTPException(404, "session not found")

@router.get("/artifacts/{artifact_id}")
def download(artifact_id: str, request: Request):
    try:
        meta, path = request.app.state.artifact_service.get(artifact_id)
        return FileResponse(path, media_type=meta["content_type"], filename=f"{artifact_id}{path.suffix}")
    except SessionNotFound:
        raise HTTPException(404, "artifact not found")
    except ArtifactError as exc:
        raise HTTPException(410, str(exc))
