from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phantom.api.app import create_app
from phantom.services.session_service import SessionService


class NoProcessSessionService(SessionService):
    def _launch(self, sid: str, profile_id: int) -> None:
        # Deterministic contract test: worker integration belongs to runtime tests.
        return


@pytest.fixture
def api(tmp_path: Path):
    data = tmp_path / "data"
    (data / "runtime").mkdir(parents=True)
    token = secrets.token_urlsafe(20)
    (data / "runtime" / ".api_token").write_text(token)
    os.environ["PHANTOM_DATA_DIR"] = str(data)
    app = create_app()
    app.state.session_service = NoProcessSessionService(max_concurrency=1)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post("/v1/profiles", headers=headers, json={"name": "session-profile"}).json()
    yield client, headers, profile
    os.environ.pop("PHANTOM_DATA_DIR", None)


def test_session_crud_capabilities_and_auth(api):
    client, headers, profile = api
    assert client.get("/v1/sessions").status_code == 403
    created = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=headers).json()
    assert created["status"] == "starting"
    assert created["capabilities"]["transport"] == "actions"
    assert "cdp_url" not in created["capabilities"]
    assert "user_data_dir" not in created
    assert client.get(f"/v1/sessions/{created['id']}", headers=headers).status_code == 200
    assert client.get("/v1/sessions", headers=headers).json()["count"] == 1
    stopped = client.delete(f"/v1/sessions/{created['id']}", headers=headers).json()
    assert stopped["status"] == "stopped"


def test_start_stop_idempotency_and_conflict(api):
    client, headers, profile = api
    h = {**headers, "Idempotency-Key": "start-one"}
    first = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=h)
    second = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=h)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    sid = first.json()["id"]
    stop_h = {**headers, "Idempotency-Key": "stop-one"}
    assert client.delete(f"/v1/sessions/{sid}", headers=stop_h).status_code == 202
    assert client.delete(f"/v1/sessions/{sid}", headers=stop_h).status_code == 200


def test_fifo_queue_and_duplicate_active_profile(api):
    client, headers, profile = api
    first = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=headers)
    assert first.status_code == 201
    assert client.post(f"/v1/profiles/{profile['id']}/sessions", headers=headers).status_code == 409
    p2 = client.post("/v1/profiles", headers=headers, json={"name": "second"}).json()
    queued = client.post(f"/v1/profiles/{p2['id']}/sessions", headers=headers).json()
    assert queued["status"] == "queued"
    client.delete(f"/v1/sessions/{first.json()['id']}", headers=headers)
    assert client.get(f"/v1/sessions/{queued['id']}", headers=headers).json()["status"] == "starting"


def test_not_found_and_invalid_last_event_id(api):
    client, headers, profile = api
    assert client.post("/v1/profiles/99999/sessions", headers=headers).status_code == 404
    assert client.get("/v1/sessions/nope", headers=headers).status_code == 404
    session = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=headers).json()
    assert client.get(f"/v1/sessions/{session['id']}/events", headers={**headers, "Last-Event-ID": "bad"}).status_code == 400
