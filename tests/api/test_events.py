from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi.testclient import TestClient

from phantom.api.app import create_app
from phantom.services.session_service import SessionService


class StaticService(SessionService):
    def _launch(self, sid: str, profile_id: int) -> None:
        return


def test_sse_replay_and_last_event_id(tmp_path: Path):
    data = tmp_path / "data"
    (data / "runtime").mkdir(parents=True)
    token = secrets.token_urlsafe(20)
    (data / "runtime" / ".api_token").write_text(token)
    os.environ["PHANTOM_DATA_DIR"] = str(data)
    try:
        app = create_app()
        service = StaticService(max_concurrency=1)
        app.state.session_service = service
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {token}"}
        profile = client.post("/v1/profiles", headers=headers, json={"name": "events"}).json()
        session = client.post(f"/v1/profiles/{profile['id']}/sessions", headers=headers).json()
        service.stop(session["id"], "done")
        all_events = service.events_after(session["id"])
        assert [e["sequence"] for e in all_events] == list(range(1, len(all_events) + 1))
        with client.stream("GET", f"/v1/sessions/{session['id']}/events", headers={**headers, "Last-Event-ID": "1"}) as response:
            text = "".join(response.iter_text())
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "id: 1\n" not in text
        assert "id: 2\n" in text
        assert "event: session.stopped" in text
    finally:
        os.environ.pop("PHANTOM_DATA_DIR", None)
