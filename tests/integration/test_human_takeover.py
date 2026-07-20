"""Linux human-takeover integration contract.

The VNC viewer controls the existing X display; these tests prove the control
plane stops agent input while that viewer owns the session and requires a new
snapshot before automation resumes.
"""
import pytest

from phantom.agent.actions import ActionError, SessionActionService
from phantom.services.lease_service import LeaseError, LeaseService


class Sessions:
    def __init__(self):
        self.events = []
    def get(self, sid):
        return {"id": sid, "status": "ready"}
    def _event(self, sid, typ, data):
        self.events.append((sid, typ, data))


class Page:
    url = "about:blank"
    def title(self): return "fixture"
    def phantom_elements(self): return []


def test_takeover_pauses_agent_then_requires_fresh_snapshot(monkeypatch, tmp_path):
    import importlib
    from phantom import db, paths
    monkeypatch.setenv("PHANTOM_DATA_DIR", str(tmp_path))
    importlib.reload(paths)
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO sessions(id,profile_id,status,user_data_dir) VALUES(?,NULL,'ready',?)", ("session-1", str(tmp_path / "profile")))
    sessions = Sessions()
    leases = LeaseService(sessions)
    agent = leases.acquire("session-1")
    actions = SessionActionService(sessions, leases, page_provider=lambda _: Page())

    takeover = leases.begin_takeover("session-1", agent["owner_token"], agent["generation"])
    with pytest.raises(ActionError, match="human takeover"):
        actions.perform("session-1", "snapshot", {}, agent["owner_token"], agent["generation"])
    with pytest.raises(LeaseError):
        leases.end_takeover("session-1", "wrong-token")

    resumed = leases.end_takeover("session-1", takeover["takeover_token"])
    with pytest.raises(ActionError, match="fresh snapshot"):
        actions.perform("session-1", "press", {"key": "Enter"}, resumed["owner_token"], resumed["generation"])
    snap = actions.perform("session-1", "snapshot", {}, resumed["owner_token"], resumed["generation"])
    assert snap["generation"] == 1
    assert any(event[1] == "takeover.started" for event in sessions.events)
    assert any(event[1] == "takeover.released" for event in sessions.events)
