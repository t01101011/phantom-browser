"""Profile CRUD REST endpoints — /v1/profiles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from phantom.api.auth import verify_token_dep
from phantom.api.models import (
    BulkImportEntry,
    BulkImportRequest,
    ProfileCloneRequest,
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
    ProfileUpdate,
)
from phantom.services import profile_service

router = APIRouter(
    prefix="/v1/profiles",
    tags=["profiles"],
    dependencies=[Depends(verify_token_dep)],
)


@router.get("", response_model=ProfileListResponse)
async def list_profiles(
    platform: str | None = Query(None, description="Filter by platform tag"),
) -> ProfileListResponse:
    """List all profiles, optionally filtered by platform_tag."""
    rows = profile_service.list_profiles(platform_tag=platform)
    profiles = [ProfileResponse(**r) for r in rows]
    return ProfileListResponse(profiles=profiles, count=len(profiles))


@router.post("", response_model=ProfileResponse, status_code=HTTP_201_CREATED)
async def create_profile(body: ProfileCreate) -> ProfileResponse:
    """Create a new browser profile with full fingerprint identity."""
    try:
        result = profile_service.create_profile(
            name=body.name,
            platform_tag=body.platform_tag,
            proxy_host=body.proxy_host,
            proxy_port=body.proxy_port,
            proxy_user=body.proxy_user,
            proxy_pass=body.proxy_pass,
            proxy_source=body.proxy_source,
            timezone=body.timezone,
            notes=body.notes,
            folder_id=body.folder_id,
            proxy_id=body.proxy_id,
            locale_language=body.locale_language,
            locale_region=body.locale_region,
            navigator_language=body.navigator_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    return ProfileResponse(**result)


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: int) -> ProfileResponse:
    """Get a single profile by ID."""
    row = profile_service.get_profile(profile_id)
    if row is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    return ProfileResponse(**row)


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: int,
    body: ProfileUpdate,
) -> ProfileResponse:
    """Update an existing profile."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    try:
        result = profile_service.update_profile(profile_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    if result is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )
    return ProfileResponse(**result)


@router.delete("/{profile_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int) -> None:
    """Delete a profile.  Refuses if the profile is running."""
    try:
        ok = profile_service.delete_profile(profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    if not ok:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found",
        )


@router.post("/{profile_id}/clone", response_model=ProfileResponse, status_code=HTTP_201_CREATED)
async def clone_profile(
    profile_id: int,
    body: ProfileCloneRequest,
) -> ProfileResponse:
    """Clone a profile with a fresh fingerprint identity."""
    try:
        result = profile_service.clone_profile(profile_id, body.new_name)
    except ValueError as exc:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=str(exc))
    return ProfileResponse(**result)


@router.post("/import/preview")
async def bulk_import_preview(body: BulkImportRequest) -> dict:
    """Preview a bulk profile import — validates without writing."""
    data = [e.model_dump() for e in body.profiles]
    return profile_service.bulk_import_preview(data)


@router.post("/import", response_model=list[dict], status_code=HTTP_201_CREATED)
async def bulk_import(body: BulkImportRequest) -> list[dict]:
    """Bulk import profiles in a single transaction."""
    data = [e.model_dump() for e in body.profiles]
    return profile_service.bulk_import_apply(data)
