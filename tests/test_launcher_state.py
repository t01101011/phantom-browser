from __future__ import annotations

from types import SimpleNamespace

from phantom import launcher


def test_launch_detached_records_child_state(tmp_path, monkeypatch):
    updates = []
    running = []
    statuses = []
    fake_profile = {"id": 7, "name": "alpha"}

    monkeypatch.setattr(launcher, "DATA_DIR", tmp_path / "profiles_data")
    monkeypatch.setattr(launcher.db, "get_profile", lambda profile_id: fake_profile)
    monkeypatch.setattr(launcher.db, "is_running", lambda profile_id: None)
    monkeypatch.setattr(
        launcher.db, "update_profile", lambda profile_id, fields: updates.append((profile_id, fields))
    )
    monkeypatch.setattr(
        launcher.db, "mark_running", lambda profile_id, pid: running.append((profile_id, pid))
    )
    monkeypatch.setattr(
        launcher.db, "set_status", lambda profile_id, status: statuses.append((profile_id, status))
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(pid=4321),
    )

    child_pid = launcher.launch_detached(7, headless="virtual", start_url="https://example.com")

    assert child_pid == 4321
    assert running == [(7, 4321)]
    assert statuses == [(7, "running")]
    assert updates == [
        (7, {"user_data_dir": str(tmp_path / "profiles_data" / "profile_7")})
    ]


def test_launch_detached_rejects_live_duplicate(monkeypatch):
    monkeypatch.setattr(launcher.db, "get_profile", lambda profile_id: {"name": "alpha"})
    monkeypatch.setattr(launcher.db, "is_running", lambda profile_id: 4321)
    monkeypatch.setattr(launcher, "_pid_alive", lambda pid: True)

    try:
        launcher.launch_detached(7)
    except RuntimeError as exc:
        assert "already running as pid 4321" in str(exc)
    else:
        raise AssertionError("duplicate launch should fail")


def test_stop_returns_false_without_running_row(monkeypatch):
    monkeypatch.setattr(launcher.db, "is_running", lambda profile_id: None)

    assert launcher.stop(7) is False


def test_pid_alive_uses_windows_process_probe(monkeypatch):
    monkeypatch.setattr(launcher, "IS_WINDOWS", True)
    monkeypatch.setattr(launcher, "_pid_dead_windows", lambda pid: pid == 12)

    assert launcher._pid_alive(11) is True
    assert launcher._pid_alive(12) is False
