"""Tests for profile CRUD REST endpoints (/v1/profiles).

Implements the RED → GREEN cycle for Task 5.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

# Set test data dir before any phantom imports
_TEST_DATA_DIR: str | None = None


def _set_data_dir(path: str) -> None:
    global _TEST_DATA_DIR
    _TEST_DATA_DIR = path
    os.environ["PHANTOM_DATA_DIR"] = path


from phantom.api.app import create_app


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "phantom_data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runtime").mkdir(exist_ok=True)
    _set_data_dir(str(d))
    yield d
    os.environ.pop("PHANTOM_DATA_DIR", None)


@pytest.fixture
def auth_token(data_dir: Path) -> str:
    token = secrets.token_urlsafe(32)
    token_path = data_dir / "runtime" / ".api_token"
    token_path.write_text(token)
    return token


@pytest.fixture
def client(data_dir: Path, auth_token: str) -> TestClient:
    app = create_app()
    return TestClient(app)


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Profile CRUD tests ─────────────────────────────────────────────────────────


class TestProfileCRUD:
    """Full CRUD cycle for /v1/profiles."""

    PROFILE_DATA = {
        "name": "test-profile-1",
        "platform_tag": "custom",
        "proxy_host": "127.0.0.1",
        "proxy_port": 8080,
        "proxy_user": "user1",
        "proxy_pass": "pass123",
    }

    def test_create_profile(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "test-profile-1"
        assert body["platform_tag"] == "custom"
        assert body["proxy_host"] == "127.0.0.1"
        assert body["proxy_port"] == 8080
        assert "proxy_pass" not in body, "proxy_pass should be redacted"
        assert "fingerprint_json" not in body, "fingerprint should be redacted"
        assert body["status"] == "idle"
        assert "id" in body
        assert "created_at" in body

    def test_create_duplicate_name_fails(self, client: TestClient, auth_token: str) -> None:
        client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        resp = client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 409, resp.text
        assert "already exists" in resp.json()["detail"]

    def test_create_missing_required_name(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/profiles",
            json={"platform_tag": "custom"},
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 422  # validation error

    def test_list_profiles(self, client: TestClient, auth_token: str) -> None:
        # Create two profiles
        client.post(
            "/v1/profiles",
            json={**self.PROFILE_DATA, "name": "prof-a"},
            headers=_auth_headers(auth_token),
        )
        client.post(
            "/v1/profiles",
            json={**self.PROFILE_DATA, "name": "prof-b", "platform_tag": "facebook"},
            headers=_auth_headers(auth_token),
        )

        resp = client.get("/v1/profiles", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert len(body["profiles"]) == 2

    def test_list_profiles_filtered(self, client: TestClient, auth_token: str) -> None:
        client.post(
            "/v1/profiles",
            json={**self.PROFILE_DATA, "name": "prof-a"},
            headers=_auth_headers(auth_token),
        )
        client.post(
            "/v1/profiles",
            json={**self.PROFILE_DATA, "name": "prof-b", "platform_tag": "facebook"},
            headers=_auth_headers(auth_token),
        )

        resp = client.get(
            "/v1/profiles?platform=facebook",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["profiles"][0]["name"] == "prof-b"

    def test_get_profile(self, client: TestClient, auth_token: str) -> None:
        create_resp = client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        pid = create_resp.json()["id"]

        resp = client.get(f"/v1/profiles/{pid}", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "test-profile-1"
        assert "proxy_pass" not in body

    def test_get_profile_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/v1/profiles/99999", headers=_auth_headers(auth_token))
        assert resp.status_code == 404

    def test_update_profile(self, client: TestClient, auth_token: str) -> None:
        create_resp = client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        pid = create_resp.json()["id"]

        resp = client.put(
            f"/v1/profiles/{pid}",
            json={"notes": "updated notes", "proxy_port": 9090},
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["notes"] == "updated notes"
        assert body["proxy_port"] == 9090

    def test_update_profile_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.put(
            "/v1/profiles/99999",
            json={"notes": "test"},
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 404

    def test_delete_profile(self, client: TestClient, auth_token: str) -> None:
        create_resp = client.post(
            "/v1/profiles",
            json=self.PROFILE_DATA,
            headers=_auth_headers(auth_token),
        )
        pid = create_resp.json()["id"]

        resp = client.delete(f"/v1/profiles/{pid}", headers=_auth_headers(auth_token))
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/v1/profiles/{pid}", headers=_auth_headers(auth_token))
        assert get_resp.status_code == 404

    def test_delete_profile_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.delete("/v1/profiles/99999", headers=_auth_headers(auth_token))
        assert resp.status_code == 404


class TestProfileClone:
    """Cloning profiles."""

    def test_clone_profile(self, client: TestClient, auth_token: str) -> None:
        create_resp = client.post(
            "/v1/profiles",
            json={
                "name": "original",
                "platform_tag": "facebook",
                "proxy_host": "10.0.0.1",
                "proxy_port": 3128,
                "proxy_user": "u1",
                "proxy_pass": "p1",
            },
            headers=_auth_headers(auth_token),
        )
        pid = create_resp.json()["id"]

        resp = client.post(
            f"/v1/profiles/{pid}/clone",
            json={"new_name": "clone-1"},
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "clone-1"
        assert body["platform_tag"] == "facebook"
        assert body["proxy_host"] == "10.0.0.1"

    def test_clone_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/profiles/99999/clone",
            json={"new_name": "ghost"},
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 409  # not found → conflict


class TestProfileAuth:
    """All profile endpoints must require authentication."""

    ENPOINTS = [
        ("GET", "/v1/profiles"),
        ("POST", "/v1/profiles"),
        ("GET", "/v1/profiles/1"),
        ("PUT", "/v1/profiles/1"),
        ("DELETE", "/v1/profiles/1"),
        ("POST", "/v1/profiles/1/clone"),
        ("POST", "/v1/profiles/import/preview"),
        ("POST", "/v1/profiles/import"),
    ]

    @pytest.mark.parametrize("method,path", ENPOINTS)
    def test_no_token_returns_403(self, client: TestClient, method: str, path: str) -> None:
        resp = client.request(method, path)
        assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}"


class TestBulkImport:
    """Bulk import preview and apply."""

    def test_bulk_import_preview(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/profiles/import/preview",
            json={
                "profiles": [
                    {"name": "bulk-a", "platform_tag": "custom", "proxy_host": "1.2.3.4", "proxy_port": 8080},
                    {"name": "", "platform_tag": "custom"},  # invalid
                ]
            },
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["valid"]) == 1
        assert len(body["errors"]) == 1

    def test_bulk_import_apply(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/profiles/import",
            json={
                "profiles": [
                    {"name": "import-a", "platform_tag": "custom", "proxy_host": "1.2.3.4", "proxy_port": 8080},
                    {"name": "import-b", "platform_tag": "facebook", "proxy_host": "5.6.7.8", "proxy_port": 3128},
                ]
            },
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert len(body) == 2
        assert body[0]["status"] == "created"
        assert body[1]["status"] == "created"

        # Verify both exist
        list_resp = client.get("/v1/profiles", headers=_auth_headers(auth_token))
        assert list_resp.json()["count"] == 2
