"""Tests for folder and proxy CRUD REST endpoints (/v1/folders, /v1/proxies).

Implements the RED → GREEN cycle for Task 5.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

# Set test data dir before any phantom imports
def _set_data_dir(path: str) -> None:
    os.environ["PHANTOM_DATA_DIR"] = path


from phantom.api.app import create_app
from phantom.db import init_db, get_conn


# ── Fixtures ────────────────────────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "phantom_data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "runtime").mkdir(exist_ok=True)
    _set_data_dir(str(d))
    init_db()  # Ensure tables exist
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


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Folder tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFolderCRUD:
    """Full CRUD cycle for /v1/folders."""

    def test_create_folder(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/folders",
            json={"name": "social-media"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "social-media"
        assert body["defaults_json"] == "{}"
        assert "id" in body

    def test_create_duplicate_name_fails(self, client: TestClient, auth_token: str) -> None:
        client.post("/v1/folders", json={"name": "dup"}, headers=_h(auth_token))
        resp = client.post("/v1/folders", json={"name": "dup"}, headers=_h(auth_token))
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_with_parent(self, client: TestClient, auth_token: str) -> None:
        parent = client.post(
            "/v1/folders", json={"name": "parent"}, headers=_h(auth_token)
        ).json()
        resp = client.post(
            "/v1/folders",
            json={"name": "child", "parent_id": parent["id"]},
            headers=_h(auth_token),
        )
        assert resp.status_code == 201
        assert resp.json()["parent_id"] == parent["id"]

    def test_create_with_invalid_parent(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/folders",
            json={"name": "orphan", "parent_id": 99999},
            headers=_h(auth_token),
        )
        assert resp.status_code == 404

    def test_list_folders(self, client: TestClient, auth_token: str) -> None:
        client.post("/v1/folders", json={"name": "a"}, headers=_h(auth_token))
        client.post("/v1/folders", json={"name": "b"}, headers=_h(auth_token))
        resp = client.get("/v1/folders", headers=_h(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert len(body["folders"]) == 2

    def test_get_folder(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/folders", json={"name": "my-folder"}, headers=_h(auth_token)
        ).json()
        resp = client.get(f"/v1/folders/{created['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-folder"

    def test_get_folder_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/v1/folders/99999", headers=_h(auth_token))
        assert resp.status_code == 404

    def test_update_folder(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/folders", json={"name": "old-name"}, headers=_h(auth_token)
        ).json()
        resp = client.put(
            f"/v1/folders/{created['id']}",
            json={"name": "new-name"},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    def test_delete_folder(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/folders", json={"name": "delete-me"}, headers=_h(auth_token)
        ).json()
        resp = client.delete(
            f"/v1/folders/{created['id']}", headers=_h(auth_token)
        )
        assert resp.status_code == 204
        # Verify gone
        get_resp = client.get(
            f"/v1/folders/{created['id']}", headers=_h(auth_token)
        )
        assert get_resp.status_code == 404

    def test_delete_folder_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.delete("/v1/folders/99999", headers=_h(auth_token))
        assert resp.status_code == 404


class TestFolderAuth:
    """All folder endpoints must require authentication."""

    ENDPOINTS = [
        ("GET", "/v1/folders"),
        ("POST", "/v1/folders"),
        ("GET", "/v1/folders/1"),
        ("PUT", "/v1/folders/1"),
        ("DELETE", "/v1/folders/1"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_no_token_returns_403(self, client: TestClient, method: str, path: str) -> None:
        resp = client.request(method, path)
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# Proxy tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestProxyCRUD:
    """Full CRUD cycle for /v1/proxies."""

    PROXY_DATA = {
        "name": "my-residential",
        "scheme": "http",
        "host": "res.example.com",
        "port": 3128,
        "username": "user123",
        "password": "secret!@#",
    }

    def test_create_proxy(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/proxies",
            json=self.PROXY_DATA,
            headers=_h(auth_token),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "my-residential"
        assert body["host"] == "res.example.com"
        assert body["password"] == "*****", "password should be redacted"
        assert body["health_status"] == "unknown"
        assert "id" in body

    def test_create_duplicate_name_fails(self, client: TestClient, auth_token: str) -> None:
        client.post("/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token))
        resp = client.post(
            "/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token)
        )
        assert resp.status_code == 409

    def test_create_invalid_port(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/proxies",
            json={**self.PROXY_DATA, "port": 99999},
            headers=_h(auth_token),
        )
        assert resp.status_code == 422  # validation error

    def test_list_proxies(self, client: TestClient, auth_token: str) -> None:
        client.post("/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token))
        client.post(
            "/v1/proxies",
            json={**self.PROXY_DATA, "name": "proxy-2", "host": "another.example.com"},
            headers=_h(auth_token),
        )
        resp = client.get("/v1/proxies", headers=_h(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert len(body["proxies"]) == 2

    def test_get_proxy(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token)
        ).json()
        resp = client.get(f"/v1/proxies/{created['id']}", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-residential"
        assert resp.json()["password"] == "*****"

    def test_get_proxy_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/v1/proxies/99999", headers=_h(auth_token))
        assert resp.status_code == 404

    def test_update_proxy(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token)
        ).json()
        resp = client.put(
            f"/v1/proxies/{created['id']}",
            json={"host": "new-host.example.com", "port": 8080},
            headers=_h(auth_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["host"] == "new-host.example.com"
        assert body["port"] == 8080

    def test_delete_proxy(self, client: TestClient, auth_token: str) -> None:
        created = client.post(
            "/v1/proxies", json=self.PROXY_DATA, headers=_h(auth_token)
        ).json()
        resp = client.delete(
            f"/v1/proxies/{created['id']}", headers=_h(auth_token)
        )
        assert resp.status_code == 204
        # Verify gone
        get_resp = client.get(
            f"/v1/proxies/{created['id']}", headers=_h(auth_token)
        )
        assert get_resp.status_code == 404

    def test_delete_proxy_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.delete("/v1/proxies/99999", headers=_h(auth_token))
        assert resp.status_code == 404


class TestProxyHealth:
    """Proxy health check endpoint."""

    def test_check_proxy_not_found(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/v1/proxies/99999/check", headers=_h(auth_token)
        )
        assert resp.status_code == 404

    # Full health check requires external connectivity — we test the DB health
    # update separately via the status field set by the check.


class TestProxyAuth:
    """All proxy endpoints must require authentication."""

    ENDPOINTS = [
        ("GET", "/v1/proxies"),
        ("POST", "/v1/proxies"),
        ("GET", "/v1/proxies/1"),
        ("PUT", "/v1/proxies/1"),
        ("DELETE", "/v1/proxies/1"),
        ("POST", "/v1/proxies/1/check"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_no_token_returns_403(self, client: TestClient, method: str, path: str) -> None:
        resp = client.request(method, path)
        assert resp.status_code == 403
