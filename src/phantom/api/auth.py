"""Token-based authentication for the Phantom local control plane.

Token lifecycle
---------------
On first startup (or when the token file does not exist), a random
``secrets.token_urlsafe(32)`` is generated and persisted to
``<runtime_dir>/.api_token`` with owner-only permissions (``0o600``).

On subsequent startups the existing token is reused so that previously
configured clients retain access.

Token comparison uses ``secrets.compare_digest`` (constant-time) to
deflect simple timing side-channel attacks on the local network.
"""
from __future__ import annotations

import secrets
import stat as _stat

from fastapi import HTTPException, Request
from starlette.status import HTTP_403_FORBIDDEN


# ── Token file ─────────────────────────────────────────────────────────────────

TOKEN_FILENAME = ".api_token"


def _token_path():
    """Resolve the token file path lazily so PHANTOM_DATA_DIR can be changed."""
    from phantom.paths import runtime_dir

    return runtime_dir / TOKEN_FILENAME


def load_or_generate_token() -> str:
    """Return the persisted API token, creating one if none exists.

    The token is stored as plain text in ``<runtime_dir>/.api_token``,
    created with ``0o600`` permissions on POSIX systems.
    """
    path = _token_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip()

    # Generate a fresh token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")

    # Restrict permissions to owner-only on POSIX
    try:
        path.chmod(_stat.S_IRUSR | _stat.S_IWUSR)  # 0o600
    except Exception:
        pass  # non-POSIX or read-only fs — best effort

    return token


# ── Auth guard ──────────────────────────────────────────────────────────────────


async def verify_token_dep(request: Request) -> None:
    """FastAPI dependency that rejects unauthenticated requests with 403.

    * Extracts the Bearer token from the ``Authorization`` header.
    * Compares it (constant-time) against the persisted token.
    * Passes through for matching tokens; raises 403 otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Missing auth header")

    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Malformed auth header — expected 'Bearer <token>'",
        )

    scheme, token = parts
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Only Bearer scheme supported",
        )

    if not token:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Empty token")

    expected = load_or_generate_token()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid auth token")
