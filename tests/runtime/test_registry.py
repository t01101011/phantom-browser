"""Tests for the ProcessRegistry (Task 7).

Uses monkeypatching/mocking to avoid real DB, real process management.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """Mock out all DB interactions so tests don't need a real database."""
    import phantom.db as db_mod

    # Mock list_profiles_by_status
    mock_list = MagicMock(return_value=[])
    monkeypatch.setattr(db_mod, "list_profiles_by_status", mock_list)

    # Mock mark_stopped / set_status / is_running
    monkeypatch.setattr(db_mod, "mark_stopped", MagicMock())
    monkeypatch.setattr(db_mod, "set_status", MagicMock())
    monkeypatch.setattr(db_mod, "is_running", MagicMock(return_value=None))

    return db_mod


@pytest.fixture
def registry():
    """Return a fresh ProcessRegistry for each test."""
    from phantom.runtime.registry import ProcessRegistry
    return ProcessRegistry()


# ── Helper: make a fake profile row ──────────────────────────────────────────


def _fake_running_row(profile_id: int, name: str = "test") -> dict:
    return {
        "id": profile_id,
        "name": name,
        "status": "running",
        "platform_tag": "facebook",
        "proxy_host": "127.0.0.1",
        "proxy_port": 8080,
        "proxy_user": "u",
        "proxy_pass": "p",
        "fingerprint_json": "{}",
        "seeds_json": "{}",
        "webgl_json": "{}",
        "fonts_json": "{}",
        "voices_json": "{}",
        "misc_json": "{}",
        "target_os": "windows",
        "timezone": "America/Denver",
        "locale_language": "en",
        "locale_region": "US",
        "navigator_language": "en-US",
        "user_data_dir": "/tmp/phantom/profile_1",
        "notes": "",
        "created_at": "2026-07-19",
        "updated_at": "2026-07-19",
    }


# ── Registry tests ────────────────────────────────────────────────────────────


class TestProcessRegistry:
    """ProcessRegistry core functionality."""

    def test_register_and_get_worker(self, registry):
        """Register a worker and retrieve its info."""
        info = registry.register(profile_id=1, pid=9999, url="https://example.com")
        assert info.profile_id == 1
        assert info.pid == 9999
        assert info.status == "starting"
        assert info.meta.get("url") == "https://example.com"
        assert info.uptime >= 0

        retrieved = registry.get_worker(1)
        assert retrieved is info  # same object

    def test_register_duplicate_raises(self, registry, monkeypatch):
        """Registering same profile twice should raise ValueError."""
        from phantom.runtime.registry import is_process_alive
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        registry.register(profile_id=1, pid=9999)
        with pytest.raises(ValueError, match="already running"):
            registry.register(profile_id=1, pid=10000)

    def test_register_duplicate_dead_allowed(self, registry, monkeypatch):
        """Registering a profile whose previous process died should succeed."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: False,
        )
        registry.register(profile_id=1, pid=9999)
        # Previous is dead — should succeed
        info = registry.register(profile_id=1, pid=10000)
        assert info.pid == 10000

    def test_unregister(self, registry):
        """Unregister must remove worker and set status to stopped."""
        registry.register(profile_id=1, pid=9999)
        removed = registry.unregister(1)
        assert removed is not None
        assert removed.status == "stopped"
        assert registry.get_worker(1) is None

    def test_unregister_nonexistent(self, registry):
        """Unregister a not-tracked profile should return None."""
        assert registry.unregister(999) is None

    def test_is_running_true(self, registry, monkeypatch):
        """is_running returns True when process is alive."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        registry.register(profile_id=1, pid=9999)
        assert registry.is_running(1) is True

    def test_is_running_false_dead(self, registry, monkeypatch):
        """is_running returns False when process is dead."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: False,
        )
        registry.register(profile_id=1, pid=9999)
        assert registry.is_running(1) is False

    def test_is_running_not_registered(self, registry):
        """is_running for untracked profile returns False."""
        assert registry.is_running(999) is False

    def test_list_workers(self, registry):
        """list_workers must return all tracked workers."""
        registry.register(profile_id=1, pid=100)
        registry.register(profile_id=2, pid=200)
        workers = registry.list_workers()
        assert len(workers) == 2
        pids = {w.pid for w in workers}
        assert pids == {100, 200}

    def test_count(self, registry):
        """count() must reflect number of registered workers."""
        assert registry.count() == 0
        registry.register(profile_id=1, pid=100)
        assert registry.count() == 1
        registry.register(profile_id=2, pid=200)
        assert registry.count() == 2
        registry.unregister(1)
        assert registry.count() == 1

    def test_len(self, registry):
        """__len__ must match count()."""
        assert len(registry) == 0
        registry.register(profile_id=1, pid=100)
        assert len(registry) == 1

    def test_repr(self, registry):
        """__repr__ must include worker count."""
        registry.register(profile_id=1, pid=100)
        r = repr(registry)
        assert "ProcessRegistry" in r
        assert "1" in r


class TestMarkReady:
    """Worker status transitions via mark_ready / mark_crashed."""

    def test_mark_ready(self, registry):
        """mark_ready must set status to 'ready'."""
        registry.register(profile_id=1, pid=9999)
        registry.mark_ready(1)
        info = registry.get_worker(1)
        assert info.status == "ready"

    def test_mark_crashed(self, registry):
        """mark_crashed must set status to 'crashed'."""
        registry.register(profile_id=1, pid=9999)
        registry.mark_crashed(1)
        info = registry.get_worker(1)
        assert info.status == "crashed"

    def test_wait_ready_blocks(self, registry):
        """wait_ready must block until mark_ready is called."""
        registry.register(profile_id=1, pid=9999)
        import threading

        def signal_ready():
            time.sleep(0.05)
            registry.mark_ready(1)

        t = threading.Thread(target=signal_ready, daemon=True)
        t.start()
        assert registry.wait_ready(1, timeout=5.0) is True
        assert registry.get_worker(1).status == "ready"

    def test_wait_ready_timeout(self, registry):
        """wait_ready must return False on timeout."""
        registry.register(profile_id=1, pid=9999)
        assert registry.wait_ready(1, timeout=0.1) is False

    def test_wait_ready_not_registered(self, registry):
        """wait_ready for untracked profile must raise."""
        from phantom.runtime.registry import ProcessRegistry
        with pytest.raises(ValueError, match="not registered"):
            registry.wait_ready(999)


class TestReconcile:
    """Stale DB entry reconciliation."""

    def test_reconcile_no_running(self, registry, _mock_db):
        """With no running profiles, reconcile must return empty list."""
        _mock_db.list_profiles_by_status.return_value = []
        assert registry.reconcile() == []

    def test_reconcile_stale_pid_dead(self, registry, _mock_db, monkeypatch):
        """A running profile with a dead PID must be marked crashed."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: False,
        )
        _mock_db.list_profiles_by_status.return_value = [
            _fake_running_row(profile_id=1)
        ]
        _mock_db.is_running.return_value = 9999  # dead PID

        result = registry.reconcile()
        assert len(result) == 1
        assert result[0]["action"] == "marked_crashed"
        assert result[0]["profile_id"] == 1
        _mock_db.mark_stopped.assert_called_once_with(1)
        _mock_db.set_status.assert_called_once_with(1, "crashed")

    def test_reconcile_alive_pid_untouched(self, registry, _mock_db, monkeypatch):
        """A running profile with an alive PID must NOT be touched."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        _mock_db.list_profiles_by_status.return_value = [
            _fake_running_row(profile_id=1)
        ]
        _mock_db.is_running.return_value = 9999

        result = registry.reconcile()
        assert result == []
        _mock_db.mark_stopped.assert_not_called()
        _mock_db.set_status.assert_not_called()

    def test_reconcile_db_empty_after_exception(self, registry, monkeypatch):
        """Reconcile must handle empty/not-initialised DB gracefully."""
        import phantom.db as db_mod

        monkeypatch.setattr(
            db_mod, "list_profiles_by_status",
            MagicMock(side_effect=Exception("DB not ready")),
        )
        assert registry.reconcile() == []


class TestStopWorker:
    """Worker stop functionality."""

    def test_stop_tracked_worker(self, registry, monkeypatch):
        """stop_worker must kill process, unregister, and clear DB."""
        import phantom.db as db_mod

        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        monkeypatch.setattr(
            "phantom.runtime.registry.kill_process_tree",
            lambda pid, **kw: {"pid": pid, "signaled": [pid], "still_alive": []},
        )
        monkeypatch.setattr(db_mod, "mark_stopped", MagicMock())
        monkeypatch.setattr(db_mod, "set_status", MagicMock())

        registry.register(profile_id=1, pid=9999)
        result = registry.stop_worker(1)

        assert result["profile_id"] == 1
        assert result.get("previous_pid") == 9999
        assert registry.get_worker(1) is None  # unregistered
        db_mod.mark_stopped.assert_called_once_with(1)
        db_mod.set_status.assert_called_once_with(1, "idle")

    def test_stop_untracked_with_db_pid(self, registry, monkeypatch):
        """stop_worker must fall back to DB is_running for untracked."""
        import phantom.db as db_mod

        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        monkeypatch.setattr(
            "phantom.runtime.registry.kill_process_tree",
            lambda pid, **kw: {"pid": pid, "signaled": [pid], "still_alive": []},
        )
        # DB says this PID is running but registry doesn't track it
        monkeypatch.setattr(db_mod, "is_running", MagicMock(return_value=8888))
        monkeypatch.setattr(db_mod, "mark_stopped", MagicMock())
        monkeypatch.setattr(db_mod, "set_status", MagicMock())

        result = registry.stop_worker(profile_id=5)
        assert result["profile_id"] == 5
        assert "previous_pid" not in result  # not tracked in-memory
        db_mod.mark_stopped.assert_called_once_with(5)
        db_mod.set_status.assert_called_once_with(5, "idle")

    def test_stop_nonexistent(self, registry, monkeypatch):
        """stop_worker for unknown profile must return 'not_found'."""
        import phantom.db as db_mod

        monkeypatch.setattr(db_mod, "is_running", MagicMock(return_value=None))
        result = registry.stop_worker(profile_id=999)
        assert result.get("error") == "not_found"


class TestStopAll:
    """Stop all workers."""

    def test_stop_all(self, registry, monkeypatch):
        """stop_all must stop all tracked workers."""
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )
        monkeypatch.setattr(
            "phantom.runtime.registry.kill_process_tree",
            lambda pid, **kw: {"pid": pid, "signaled": [pid], "still_alive": []},
        )

        registry.register(profile_id=1, pid=100)
        registry.register(profile_id=2, pid=200)
        results = registry.stop_all()

        assert len(results) == 2
        assert registry.count() == 0

    def test_stop_all_empty(self, registry):
        """stop_all with no workers must return empty list."""
        assert registry.stop_all() == []


@pytest.mark.skipif(sys.platform == "win32", reason="Linux /proc semantics")
def test_linux_zombie_is_dead_and_owned_child_is_reaped():
    """A terminated child must not remain a live registry survivor."""
    from phantom.runtime.process_linux import is_process_alive, kill_process_tree

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        result = kill_process_tree(
            child.pid, sigterm_timeout=0.05, sigkill_delay=0.05
        )
        assert result["still_alive"] == []
        assert not is_process_alive(child.pid)
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
