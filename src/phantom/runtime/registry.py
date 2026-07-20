"""Cross-platform worker registry.

Tracks running browser worker processes, reconciles stale DB entries,
and provides cleanup on crash/shutdown.
"""
from __future__ import annotations

import os
import platform
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from phantom import db


@dataclass
class WorkerInfo:
    """Runtime metadata for a tracked worker process."""

    profile_id: int
    pid: int
    status: str = "starting"  # starting | ready | stopping | crashed | stopped
    started_at: float = field(default_factory=time.monotonic)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def uptime(self) -> float:
        """Seconds since this worker was registered."""
        return time.monotonic() - self.started_at


# Platform detection and helper routing
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    from phantom.runtime import process_windows as _proc
else:
    from phantom.runtime import process_linux as _proc


def is_process_alive(pid: int) -> bool:
    """Cross-platform process existence check."""
    return _proc.is_process_alive(pid)


def kill_process_tree(pid: int, **kwargs: Any) -> dict[str, Any]:
    """Cross-platform process tree termination."""
    return _proc.kill_process_tree(pid, **kwargs)


def get_process_info(pid: int) -> dict[str, Any]:
    """Cross-platform process resource info."""
    return _proc.get_process_info(pid)


class ProcessRegistry:
    """In-memory registry of running worker processes.

    Thread-safe.  Provides duplicate-launch prevention, stale-DB
    reconciliation, and stop-all.

    Usage
    -----
    .. code-block:: python

        reg = ProcessRegistry()
        reg.reconcile()                          # cleanup stale DB entries
        reg.register(1, 12345)                   # track a new worker
        reg.wait_ready(1, timeout=30.0)          # wait for ready signal
        w = reg.get_worker(1)                    # retrieve WorkerInfo
        reg.stop_worker(1)                       # stop + cleanup
    """

    def __init__(self) -> None:
        self._workers: dict[int, WorkerInfo] = {}
        self._lock = threading.Lock()
        self._ready_events: dict[int, threading.Event] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def reconcile(self) -> list[dict[str, Any]]:
        """Check all 'running' profiles in DB; mark stale entries as crashed.

        Returns a list of reconciliation result dicts.
        """
        reconciled: list[dict[str, Any]] = []

        try:
            running = db.list_profiles_by_status("running")
        except Exception:
            # DB not initialised or empty
            return reconciled

        for row in running:
            profile_id = row["id"]
            pid = db.is_running(profile_id)
            if pid and not is_process_alive(pid):
                try:
                    db.mark_stopped(profile_id)
                    db.set_status(profile_id, "crashed")
                except Exception:
                    pass
                reconciled.append({
                    "profile_id": profile_id,
                    "old_pid": pid,
                    "action": "marked_crashed",
                })

        return reconciled

    def register(
        self,
        profile_id: int,
        pid: int,
        **meta: Any,
    ) -> WorkerInfo:
        """Register a worker process.

        Raises ``ValueError`` if the profile is already tracked and alive.
        """
        with self._lock:
            existing = self._workers.get(profile_id)
            if existing and is_process_alive(existing.pid):
                raise ValueError(
                    f"profile {profile_id} already running as pid {existing.pid}"
                )

            info = WorkerInfo(
                profile_id=profile_id,
                pid=pid,
                meta=meta,
            )
            self._workers[profile_id] = info
            self._ready_events[profile_id] = threading.Event()

        return info

    def mark_ready(self, profile_id: int) -> None:
        """Signal that a worker has reached 'ready' status."""
        with self._lock:
            info = self._workers.get(profile_id)
            if info:
                info.status = "ready"
            ev = self._ready_events.get(profile_id)
            if ev:
                ev.set()

    def mark_crashed(self, profile_id: int) -> None:
        """Mark a worker as crashed (process exited unexpectedly)."""
        with self._lock:
            info = self._workers.get(profile_id)
            if info:
                info.status = "crashed"
            ev = self._ready_events.get(profile_id)
            if ev:
                ev.set()  # unblock any waiters

    def unregister(self, profile_id: int) -> WorkerInfo | None:
        """Remove from in-memory tracking. Returns removed info or None."""
        with self._lock:
            info = self._workers.pop(profile_id, None)
            self._ready_events.pop(profile_id, None)
            if info:
                info.status = "stopped"
        return info

    # ── Queries ────────────────────────────────────────────────────────────────

    def is_running(self, profile_id: int) -> bool:
        """Check if a worker is tracked and its process is alive."""
        with self._lock:
            info = self._workers.get(profile_id)
            if info is None:
                return False
            return is_process_alive(info.pid)

    def get_worker(self, profile_id: int) -> WorkerInfo | None:
        """Return ``WorkerInfo`` for a profile, or None."""
        with self._lock:
            return self._workers.get(profile_id)

    def list_workers(self) -> list[WorkerInfo]:
        """Return all tracked workers."""
        with self._lock:
            return list(self._workers.values())

    def count(self) -> int:
        """Number of currently tracked workers."""
        with self._lock:
            return len(self._workers)

    # ── Wait / Timeout ─────────────────────────────────────────────────────────

    def wait_ready(self, profile_id: int, timeout: float = 30.0) -> bool:
        """Block until a worker signals 'ready', or timeout.

        Returns True if worker is ready, False on timeout.
        Raises ``ValueError`` if profile is not registered.
        """
        ev = self._ready_events.get(profile_id)
        if ev is None:
            raise ValueError(f"profile {profile_id} not registered")
        return ev.wait(timeout=timeout)

    # ── Stop ──────────────────────────────────────────────────────────────────

    def stop_worker(
        self,
        profile_id: int,
        **kill_kwargs: Any,
    ) -> dict[str, Any]:
        """Stop a specific worker process.

        Kills the process tree, unregisters, and clears DB.

        Returns a result dict with status and details.
        """
        with self._lock:
            info = self._workers.get(profile_id)

        if info is None:
            # Not in in-memory registry — check DB
            pid = None
            try:
                running = db.is_running(profile_id)
                if running:
                    pid = running
            except Exception:
                pass

            if pid:
                result = kill_process_tree(pid, **kill_kwargs)
                try:
                    db.mark_stopped(profile_id)
                    db.set_status(profile_id, "idle")
                except Exception:
                    pass
                result["profile_id"] = profile_id
                return result

            return {"profile_id": profile_id, "error": "not_found"}

        result = kill_process_tree(info.pid, **kill_kwargs)
        with self._lock:
            self._workers.pop(profile_id, None)
            self._ready_events.pop(profile_id, None)

        try:
            db.mark_stopped(profile_id)
            db.set_status(profile_id, "idle")
        except Exception:
            pass

        result["profile_id"] = profile_id
        result["previous_pid"] = info.pid
        return result

    def stop_all(self, **kill_kwargs: Any) -> list[dict[str, Any]]:
        """Stop all tracked workers.

        Returns a list of result dicts.
        """
        results: list[dict[str, Any]] = []
        with self._lock:
            profile_ids = list(self._workers.keys())

        for pid in profile_ids:
            results.append(self.stop_worker(pid, **kill_kwargs))

        return results

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return f"<ProcessRegistry workers={self.count()}>"
