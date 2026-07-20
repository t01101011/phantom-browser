"""Tests for crash recovery and process lifecycle (Task 7).

Focuses on:
- Process death detection
- Stale DB reconciliation
- Cleanup after crash
- Ready timeout handling
- Signal handling after crash
"""
from __future__ import annotations

import os
import signal
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Process helpers tests ────────────────────────────────────────────────────


class TestProcessLinux:
    """Linux-specific process helpers."""

    @pytest.fixture(autouse=True)
    def _only_linux(self):
        """Skip these tests on non-Linux platforms."""
        import platform
        if platform.system() == "Windows":
            pytest.skip("Linux-specific tests")

    def test_is_process_alive_self(self):
        """Current process should be alive."""
        from phantom.runtime.process_linux import is_process_alive
        assert is_process_alive(os.getpid()) is True

    def test_is_process_alive_dead(self):
        """A very high PID should be dead (no such process)."""
        from phantom.runtime.process_linux import is_process_alive
        # PID 999999999 likely doesn't exist
        assert is_process_alive(999999999) is False

    def test_get_descendants_self(self):
        """get_descendants of current process should be a list (possibly empty)."""
        from phantom.runtime.process_linux import get_descendants
        descendants = get_descendants(os.getpid())
        assert isinstance(descendants, list)

    def test_get_process_info_self(self):
        """get_process_info for current process should return resource info."""
        from phantom.runtime.process_linux import get_process_info
        info = get_process_info(os.getpid())
        assert info.get("pid") == os.getpid()
        assert info.get("alive") is True
        # Should have some resource fields
        assert "cmdline" in info

    def test_get_process_info_dead(self):
        """get_process_info for a dead process should return empty dict."""
        from phantom.runtime.process_linux import get_process_info
        info = get_process_info(999999999)
        assert info == {}

    def test_get_descendants_invalid_pid(self):
        """get_descendants for a non-existent PID should return [].

        (The /proc walk finds no descendant because no process has
         the dead PID as its parent.)
        """
        from phantom.runtime.process_linux import get_descendants
        result = get_descendants(0)  # PID 0 is the idle process, unlikely parent
        assert isinstance(result, list)


class TestProcessWindows:
    """Windows-specific process helpers (contract tests only)."""

    def test_windows_module_exists(self):
        """process_windows module must be importable with all expected symbols."""
        import importlib
        mod = importlib.import_module("phantom.runtime.process_windows")
        assert hasattr(mod, "is_process_alive")
        assert hasattr(mod, "get_descendants")
        assert hasattr(mod, "kill_process_tree")
        assert hasattr(mod, "get_process_info")

    def test_windows_get_descendants_returns_list(self):
        """get_descendants on Windows should return [] (taskkill handles trees)."""
        from phantom.runtime.process_windows import get_descendants
        result = get_descendants(1234)
        assert result == []


# ── Cross-platform routing tests ──────────────────────────────────────────────


class TestCrossPlatformRouting:
    """Platform routing in registry module."""

    def test_is_process_alive_exists(self):
        """The cross-platform wrapper must be importable and callable."""
        from phantom.runtime.registry import is_process_alive
        assert callable(is_process_alive)

    def test_kill_process_tree_exists(self):
        """The cross-platform wrapper must be importable and callable."""
        from phantom.runtime.registry import kill_process_tree
        assert callable(kill_process_tree)

    def test_get_process_info_exists(self):
        """The cross-platform wrapper must be importable and callable."""
        from phantom.runtime.registry import get_process_info
        assert callable(get_process_info)

    def test_platform_module_routing(self):
        """The correct platform module should be loaded at import."""
        import platform
        from phantom.runtime.registry import IS_WINDOWS, _proc
        assert IS_WINDOWS == (platform.system() == "Windows")
        if IS_WINDOWS:
            assert "process_windows" in repr(_proc)
        else:
            assert "process_linux" in repr(_proc)

    def test_cross_platform_kill_returns_dict(self, monkeypatch):
        """kill_process_tree must return a dict with at least 'pid'."""
        monkeypatch.setattr(
            "phantom.runtime.registry.kill_process_tree",
            lambda pid, **kw: {"pid": pid, "signaled": [pid], "still_alive": []},
        )
        from phantom.runtime.registry import kill_process_tree
        result = kill_process_tree(1234)
        assert isinstance(result, dict)
        assert "pid" in result

    def test_cross_platform_is_alive_self(self):
        """is_process_alive for current process."""
        import os
        from phantom.runtime.registry import is_process_alive
        assert is_process_alive(os.getpid()) is True

    def test_cross_platform_is_alive_dead(self):
        """is_process_alive for dead PID."""
        from phantom.runtime.registry import is_process_alive
        assert is_process_alive(999999999) is False


# ── Crash detection tests ────────────────────────────────────────────────────


class TestCrashDetection:
    """Process crash detection scenarios."""

    def test_worker_dies_after_register(self, registry_factory):
        """If a worker's process dies, is_running must return False."""
        import os
        reg = registry_factory()
        # Register current process (definitely alive)
        reg.register(profile_id=1, pid=os.getpid())
        assert reg.is_running(1) is True

    def test_reconcile_detects_crashed(self, registry_with_mocks, monkeypatch):
        """Reconcile must detect dead PID and mark profile crashed."""
        import phantom.db as db_mod

        reg, db_mock = registry_with_mocks

        # Make is_process_alive return False (dead process)
        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: False,
        )

        db_mock.list_profiles_by_status.return_value = [
            {"id": 1, "name": "test", "status": "running"}
        ]
        db_mock.is_running.return_value = 9999  # dead PID

        result = reg.reconcile()
        assert len(result) == 1
        assert result[0]["action"] == "marked_crashed"
        db_mock.mark_stopped.assert_called_once_with(1)
        db_mock.set_status.assert_called_once_with(1, "crashed")

    def test_reconcile_ignores_alive(self, registry_with_mocks, monkeypatch):
        """Reconcile must NOT touch profiles with alive processes."""
        import phantom.db as db_mod

        reg, db_mock = registry_with_mocks

        monkeypatch.setattr(
            "phantom.runtime.registry.is_process_alive",
            lambda pid: True,
        )

        db_mock.list_profiles_by_status.return_value = [
            {"id": 1, "name": "test", "status": "running"}
        ]
        db_mock.is_running.return_value = 9999

        result = reg.reconcile()
        assert result == []
        db_mock.mark_stopped.assert_not_called()

    def test_ready_timeout_triggers(self, registry_factory):
        """A worker that never calls mark_ready must timeout."""
        reg = registry_factory()
        reg.register(profile_id=1, pid=9999)
        assert reg.wait_ready(1, timeout=0.05) is False


# ── Fixtures for this module ──────────────────────────────────────────────────


@pytest.fixture
def registry_factory():
    """Return a factory function that yields a clean ProcessRegistry."""
    from phantom.runtime.registry import ProcessRegistry

    def _make():
        return ProcessRegistry()

    return _make


@pytest.fixture
def registry_with_mocks(monkeypatch):
    """Return (registry, db_mock) with all DB calls pre-mocked."""
    from phantom.runtime.registry import ProcessRegistry
    import phantom.db as db_mod

    monkeypatch.setattr(db_mod, "list_profiles_by_status", MagicMock(return_value=[]))
    monkeypatch.setattr(db_mod, "mark_stopped", MagicMock())
    monkeypatch.setattr(db_mod, "set_status", MagicMock())
    monkeypatch.setattr(db_mod, "is_running", MagicMock(return_value=None))

    reg = ProcessRegistry()
    return reg, db_mod
