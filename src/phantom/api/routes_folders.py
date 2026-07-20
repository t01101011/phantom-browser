"""Folder CRUD REST endpoints — /v1/folders."""
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
    FolderCreate,
    FolderListResponse,
    FolderResponse,
    FolderUpdate,
)
from phantom.db import get_conn

router = APIRouter(
    prefix="/v1/folders",
    tags=["folders"],
    dependencies=[Depends(verify_token_dep)],
)


@router.get("", response_model=FolderListResponse)
async def list_folders() -> FolderListResponse:
    """List all folders."""
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM folders ORDER BY name"
        ).fetchall()
        folders = [FolderResponse(**dict(r)) for r in rows]
        return FolderListResponse(folders=folders, count=len(folders))


@router.post("", response_model=FolderResponse, status_code=HTTP_201_CREATED)
async def create_folder(body: FolderCreate) -> FolderResponse:
    """Create a new folder for organising profiles."""
    # Validate parent exists
    if body.parent_id is not None:
        with get_conn() as c:
            parent = c.execute(
                "SELECT id FROM folders WHERE id=?", (body.parent_id,)
            ).fetchone()
            if not parent:
                raise HTTPException(
                    status_code=HTTP_404_NOT_FOUND,
                    detail=f"Parent folder {body.parent_id} not found",
                )

    with get_conn() as c:
        # Check name uniqueness
        existing = c.execute(
            "SELECT id FROM folders WHERE name=?", (body.name,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Folder name '{body.name}' already exists",
            )
        cur = c.execute(
            """INSERT INTO folders (name, parent_id, defaults_json)
               VALUES (?, ?, ?)""",
            (body.name, body.parent_id, body.defaults_json),
        )
        new_id = cur.lastrowid
        row = dict(
            c.execute("SELECT * FROM folders WHERE id=?", (new_id,)).fetchone()
        )
    return FolderResponse(**row)


@router.get("/{folder_id}", response_model=FolderResponse)
async def get_folder(folder_id: int) -> FolderResponse:
    """Get a single folder by ID."""
    with get_conn() as c:
        row = c.execute(
            "SELECT * FROM folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Folder {folder_id} not found",
            )
        return FolderResponse(**dict(row))


@router.put("/{folder_id}", response_model=FolderResponse)
async def update_folder(folder_id: int, body: FolderUpdate) -> FolderResponse:
    """Update a folder."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    with get_conn() as c:
        existing = c.execute(
            "SELECT id FROM folders WHERE id=?", (folder_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Folder {folder_id} not found",
            )

        # Check name uniqueness
        if "name" in fields:
            dup = c.execute(
                "SELECT id FROM folders WHERE name=? AND id!=?",
                (fields["name"], folder_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=HTTP_409_CONFLICT,
                    detail=f"Folder name '{fields['name']}' already exists",
                )

        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [folder_id]
        c.execute(
            f"UPDATE folders SET {sets}, updated_at=datetime('now') WHERE id=?",
            vals,
        )
        row = dict(
            c.execute(
                "SELECT * FROM folders WHERE id=?", (folder_id,)
            ).fetchone()
        )
    return FolderResponse(**row)


@router.delete("/{folder_id}", status_code=HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: int) -> None:
    """Delete a folder."""
    with get_conn() as c:
        # Check if any profiles reference this folder
        ref_count = c.execute(
            "SELECT COUNT(*) AS n FROM profiles WHERE folder_id=?", (folder_id,)
        ).fetchone()["n"]
        if ref_count > 0:
            raise HTTPException(
                status_code=HTTP_409_CONFLICT,
                detail=f"Cannot delete folder {folder_id}: {ref_count} profile(s) reference it",
            )

        cur = c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Folder {folder_id} not found",
            )
