"""Profile service — transaction-safe profile CRUD, clone, import.

Every public function takes an optional ``conn`` kwarg so callers can
share a transaction.  When ``conn`` is omitted a fresh connection is
acquired (auto-commit).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from phantom import db, identity, paths, presets
from phantom.settings import redact_dict


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_conn(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    return conn if conn is not None else db.get_conn()


_SECRET_FIELDS = (
    "proxy_pass",
    "fingerprint_json",
    "seeds_json",
    "webgl_json",
    "fonts_json",
    "voices_json",
    "misc_json",
)


def _public_profile(row: Optional[dict]) -> Optional[dict]:
    """Strip secret fields from a profile dict for API responses."""
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in _SECRET_FIELDS}


# ── CRUD ───────────────────────────────────────────────────────────────────────


def create_profile(
    name: str,
    platform_tag: str,
    proxy_host: str,
    proxy_port: int,
    proxy_user: str = "",
    proxy_pass: str = "",
    proxy_source: str = "manual",
    timezone: Optional[str] = None,
    notes: str = "",
    folder_id: Optional[int] = None,
    proxy_id: Optional[int] = None,
    locale_language: str = "en",
    locale_region: str = "US",
    navigator_language: str = "en-US",
    target_os: str = "windows",
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """Create a new profile with full fingerprint identity.

    Returns the created profile dict (public fields only).
    Raises ``ValueError`` on duplicate name or invalid platform.
    """
    preset = presets.get_preset(platform_tag)
    if preset.get("proxy_required") and not proxy_host:
        raise ValueError(
            f"Platform '{platform_tag}' requires a proxy (host:port)"
        )

    # Check name uniqueness
    c = _get_conn(conn)
    existing = c.execute(
        "SELECT id FROM profiles WHERE name=?", (name,)
    ).fetchone()
    if existing:
        raise ValueError(f"Profile name '{name}' already exists")

    blobs = identity.generate_identity(target_os=preset["target_os"])
    tz = timezone or preset.get("timezone_default")
    user_data_dir = str(paths.profiles_dir / f"profile_{name}")

    row = {
        "name":               name,
        "platform_tag":       preset["platform_tag"],
        "target_os":          preset["target_os"],
        "proxy_host":         proxy_host,
        "proxy_port":         proxy_port,
        "proxy_user":         proxy_user,
        "proxy_pass":         proxy_pass,
        "proxy_source":       proxy_source,
        "timezone":           tz,
        "locale_language":    locale_language,
        "locale_region":      locale_region,
        "navigator_language": navigator_language,
        "user_data_dir":      user_data_dir,
        "notes":              notes or preset.get("notes_default", ""),
        "folder_id":          folder_id,
        "proxy_id":           proxy_id,
        **blobs,
    }
    pid = db.create_profile(row, conn=conn)
    return _public_profile(db.get_profile(pid, conn=conn))


def get_profile(profile_id: int) -> Optional[dict]:
    """Return a profile row (public fields) or None."""
    row = db.get_profile(profile_id)
    return _public_profile(row)


def list_profiles(platform_tag: Optional[str] = None) -> list[dict]:
    """List profiles, optionally filtered by platform_tag."""
    return [_public_profile(r) for r in db.list_profiles(platform_tag)]


def update_profile(
    profile_id: int,
    fields: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Update profile fields.  Returns updated profile or None if not found.

    Allowed fields are validated.  ``proxy_pass`` and identity blobs can
    be updated but are NOT returned in the response.
    """
    allowed = {
        "name", "platform_tag", "target_os",
        "proxy_host", "proxy_port", "proxy_user", "proxy_pass",
        "proxy_source", "timezone",
        "locale_language", "locale_region", "navigator_language",
        "notes", "status",
        "folder_id", "proxy_id",
    }
    given = {k: v for k, v in fields.items() if k in allowed}
    if not given:
        raise ValueError("No valid fields to update")

    row = db.get_profile(profile_id)
    if row is None:
        return None

    # Check name uniqueness if name is being changed
    if "name" in given and given["name"] != row["name"]:
        c = _get_conn(conn)
        existing = c.execute(
            "SELECT id FROM profiles WHERE name=?", (given["name"],)
        ).fetchone()
        if existing:
            raise ValueError(f"Profile name '{given['name']}' already exists")

    db.update_profile(profile_id, given)
    return _public_profile(db.get_profile(profile_id))


def delete_profile(profile_id: int) -> bool:
    """Delete a profile.  Refuses if running."""
    if db.is_running(profile_id):
        raise RuntimeError("Profile is running — stop it before deleting")
    rc = db.delete_profile(profile_id)
    return rc > 0


def clone_profile(profile_id: int, new_name: str) -> dict:
    """Clone a profile with a new name and fresh identity."""
    row = db.get_profile(profile_id)
    if row is None:
        raise ValueError(f"Profile {profile_id} not found")

    existing = db.get_profile_by_name(new_name)
    if existing:
        raise ValueError(f"Profile name '{new_name}' already exists")

    blobs = identity.generate_identity(target_os=row["target_os"])
    new_row = {
        "name":               new_name,
        "platform_tag":       row["platform_tag"],
        "target_os":          row["target_os"],
        "proxy_host":         row["proxy_host"],
        "proxy_port":         row["proxy_port"],
        "proxy_user":         row["proxy_user"],
        "proxy_pass":         row["proxy_pass"],
        "proxy_source":       row["proxy_source"],
        "timezone":           row["timezone"],
        "locale_language":    row["locale_language"],
        "locale_region":      row["locale_region"],
        "navigator_language": row["navigator_language"],
        "user_data_dir":      str(paths.profiles_dir / f"profile_{new_name}"),
        "notes":              row["notes"],
        "folder_id":          row.get("folder_id"),
        "proxy_id":           row.get("proxy_id"),
        **blobs,
    }
    pid = db.create_profile(new_row)
    return _public_profile(db.get_profile(pid))


# ── Bulk import (preview / apply) ──────────────────────────────────────────────


def bulk_import_preview(profiles_data: list[dict]) -> dict:
    """Validate a list of profile-creation dicts and report issues.

    Returns ``{"valid": [...], "warnings": [...], "errors": [...]}``.
    No DB writes.
    """
    valid = []
    warnings = []
    errors = []
    for i, entry in enumerate(profiles_data):
        try:
            name = entry.get("name", "").strip()
            if not name:
                errors.append({"index": i, "reason": "name is required"})
                continue

            plat = entry.get("platform_tag", "custom")
            preset = presets.get_preset(plat)

            host = entry.get("proxy_host", "")
            port = entry.get("proxy_port", 0)
            if preset.get("proxy_required") and not host:
                errors.append({
                    "index": i, "name": name,
                    "reason": f"platform '{plat}' requires proxy",
                })
                continue

            dup = db.proxy_usage_count(host, port)
            if dup > 0:
                warnings.append({
                    "index": i, "name": name,
                    "reason": f"proxy {host}:{port} used by {dup} existing profile(s)",
                })

            valid.append({"index": i, "name": name, "platform": plat})
        except Exception as exc:
            errors.append({"index": i, "name": entry.get("name", ""), "reason": str(exc)})

    return {"valid": valid, "warnings": warnings, "errors": errors}


def bulk_import_apply(profiles_data: list[dict]) -> list[dict]:
    """Import profiles in bulk.  Returns list of result dicts.

    Each result has ``{"index", "name", "status", "profile"? "error"?}``.
    Uses a single transaction.
    """
    results = []
    with db.get_conn() as conn:
        for i, entry in enumerate(profiles_data):
            name = entry.get("name", "").strip()
            try:
                if not name:
                    raise ValueError("name is required")

                plat = entry.get("platform_tag", "custom")
                host = entry.get("proxy_host", "")
                port = int(entry.get("proxy_port", 0))
                user = entry.get("proxy_user", "")
                pwd = entry.get("proxy_pass", "")
                tz = entry.get("timezone")
                notes = entry.get("notes", "")

                profile = create_profile(
                    name=name,
                    platform_tag=plat,
                    proxy_host=host,
                    proxy_port=port,
                    proxy_user=user,
                    proxy_pass=pwd,
                    timezone=tz,
                    notes=notes,
                    conn=conn,
                )
                results.append({
                    "index": i,
                    "name": name,
                    "status": "created",
                    "profile": profile,
                })
            except (ValueError, RuntimeError) as exc:
                results.append({
                    "index": i,
                    "name": name,
                    "status": "error",
                    "error": str(exc),
                })
    return results


# ── Proxy usage count ──────────────────────────────────────────────────────────


def proxy_usage_count(host: str, port: int, exclude_profile_id: Optional[int] = None) -> int:
    return db.proxy_usage_count(host, port, exclude_profile_id)
