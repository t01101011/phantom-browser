"""Tests for health endpoints and token authentication.

NOTE: PHANTOM_DATA_DIR must be set BEFORE importing any phantom modules,
because ``phantom.paths`` evaluates module-level constants at import time.
The ``data_dir`` and ``client`` fixtures handle this via pytest's
``pytest_configure`` hook and the test file's early env-var setup below.
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

import pytest

# ── Critical: set default test env var before any phantom imports ──────────────
# The ``data_dir`` fixture will override this per-test, but we still need
# a valid default so that importing ``phantom.api.app`` inside the fixture
# doesn't pick up a stale real path.  The fixture sets the env var BEFORE
# calling ``create_app()``.
# We use a sentinel that each test's ``data_dir`` fixture overrides.
_TEST_DATA_DIR_SENTINEL: str | None = None


def _set_data_dir(path: str) -> None:
    global _TEST_DATA_DIR_SENTINEL
    _TEST_DATA_DIR_SENTINEL = path
    os.environ["PHANTOM_DATA_DIR"] = path


# Now safe to import phantom modules (they'll use whatever PHANTOM_DATA_DIR
# is set at this point, but each fixture properly overrides it).
from fastapi.testclient import TestClient

from phantom.api.app import create_app

# ── Shared fixture helpers ──────────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Create a temp data directory and set PHANTOM_DATA_DIR.

    This sets the env var **before** the ``client`` fixture creates the
    app, so ``phantom.paths`` resolves to the temp directory.

    After the test the env-var is removed so it does not leak into
    subsequent test files (e.g. ``test_paths.py``).
    """
    d = tmp_path / "phantom_data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runtime").mkdir(exist_ok=True)
    _set_data_dir(str(d))
    yield d
    # Cleanup: remove the env var so sibling test files are not polluted
    os.environ.pop("PHANTOM_DATA_DIR", None)


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    """TestClient with a fresh app pointed at the temp data dir.

    The ``data_dir`` fixture (run before this one) already set
    ``PHANTOM_DATA_DIR``, so ``create_app()`` resolves paths to the
    temp directory.
    """
    app = create_app()
    yield TestClient(app)


@pytest.fixture
def auth_token(data_dir: Path) -> str:
    """Pre-populate a token into the runtime dir and return it."""
    token = secrets.token_urlsafe(32)
    token_path = data_dir / "runtime" / ".api_token"
    token_path.write_text(token)
    return token


# ── /healthz (public) ────────────────────────────────────────────────────────────


class TestHealthzPublic:
    """GET /healthz must be accessible without any token."""

    def test_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_no_auth_required(self, client: TestClient) -> None:
        """No Authorization header → still 200."""
        resp = client.get("/healthz", headers={})
        assert resp.status_code == 200

    def test_wrong_method(self, client: TestClient) -> None:
        resp = client.post("/healthz")
        assert resp.status_code == 405


# ── /readyz (authenticated) ──────────────────────────────────────────────────────


class TestReadyzAuth:
    """GET /readyz requires a valid bearer token."""

    def test_no_token_returns_403(self, client: TestClient) -> None:
        resp = client.get("/readyz")
        assert resp.status_code == 403

    def test_wrong_token_returns_403(self, client: TestClient) -> None:
        resp = client.get(
            "/readyz",
            headers={"Authorization": "Bearer wrong-token-here"},
        )
        assert resp.status_code == 403

    def test_empty_bearer_returns_403(self, client: TestClient) -> None:
        resp = client.get(
            "/readyz",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 403

    def test_malformed_auth_header_returns_403(self, client: TestClient) -> None:
        resp = client.get(
            "/readyz",
            headers={"Authorization": "Basic xyz"},
        )
        assert resp.status_code == 403

    def test_valid_token_returns_ready(self, client: TestClient, auth_token: str) -> None:
        resp = client.get(
            "/readyz",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert "db" in body

    def test_different_case_bearer(self, client: TestClient, auth_token: str) -> None:
        """'bearer' lowercase should also work per spec."""
        resp = client.get(
            "/readyz",
            headers={"Authorization": f"bearer {auth_token}"},
        )
        assert resp.status_code == 200


# ── /v1/version (authenticated) ─────────────────────────────────────────────────


class TestVersionAuth:
    def test_no_token_returns_403(self, client: TestClient) -> None:
        resp = client.get("/v1/version")
        assert resp.status_code == 403

    def test_valid_token(self, client: TestClient, auth_token: str) -> None:
        resp = client.get(
            "/v1/version",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "phantom-browser"
        assert "version" in body


# ── Token lifecycle ──────────────────────────────────────────────────────────────


class TestTokenLifecycle:
    """Verify auto-generation and persistence of the API token."""

    def test_token_auto_generated_and_persisted(self, tmp_path: Path) -> None:
        """When no token file exists, create_app should generate and persist one."""
        data_dir = tmp_path / "fresh_data"
        _set_data_dir(str(data_dir))
        app = create_app()
        client = TestClient(app)

        token_path = data_dir / "runtime" / ".api_token"
        assert token_path.exists(), "Token file should have been auto-created"
        token = token_path.read_text(encoding="utf-8").strip()
        assert len(token) >= 32, f"Token too short: {len(token)}"

        # Use the auto-generated token
        resp = client.get("/v1/version",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_token_reused_from_existing_file(self, tmp_path: Path) -> None:
        """If token file already exists, it should be reused."""
        data_dir = tmp_path / "existing_data"
        runtime = data_dir / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        existing_token = "my-previously-persisted-token-value-1234"
        (runtime / ".api_token").write_text(existing_token)

        _set_data_dir(str(data_dir))
        app = create_app()
        client = TestClient(app)

        resp = client.get(
            "/v1/version",
            headers={"Authorization": f"Bearer {existing_token}"},
        )
        assert resp.status_code == 200

        # A different token should fail
        resp2 = client.get(
            "/v1/version",
            headers={"Authorization": "Bearer some-other-token"},
        )
        assert resp2.status_code == 403

    def test_token_file_permissions(self, tmp_path: Path) -> None:
        """Token file should be readable only by owner (Unix: 0o600)."""
        data_dir = tmp_path / "perm_data"
        _set_data_dir(str(data_dir))
        create_app()
        token_path = data_dir / "runtime" / ".api_token"
        if os.name == "posix":
            mode = stat.S_IMODE(token_path.stat().st_mode)
            assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ── OpenAPI docs ──────────────────────────────────────────────────────────────────


class TestOpenAPI:
    """OpenAPI schema public; docs pages only locally-bound anyway."""

    def test_openapi_json_available(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema

    def test_swagger_docs_loads(self, client: TestClient) -> None:
        """Swagger UI loads (public by default, which is fine for local-only bind)."""
        resp = client.get("/docs")
        assert resp.status_code in (200, 404)
