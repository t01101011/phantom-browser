"""Persistent browser-session orchestration and durable event log."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from phantom import db, paths
from phantom.runtime.registry import ProcessRegistry

TERMINAL = {"stopped", "crashed"}
ACTIVE = {"starting", "ready", "stopping"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionConflict(ValueError):
    pass


class SessionNotFound(LookupError):
    pass


class SessionService:
    """Thread-safe coordinator. Runtime handles remain local; state/events survive restarts."""

    def __init__(self, *, max_concurrency: int | None = None,
                 spawn: Callable[[int], subprocess.Popen[str]] | None = None) -> None:
        self.max_concurrency = max_concurrency or int(os.getenv("PHANTOM_MAX_SESSIONS", "4"))
        if self.max_concurrency < 1:
            raise ValueError("max concurrency must be positive")
        self._spawn = spawn or self._spawn_worker
        self._registry = ProcessRegistry()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.RLock()
        self._action_condition = threading.Condition()
        self._action_results: dict[str, dict[str, Any]] = {}
        self.reconcile()

    @staticmethod
    def _spawn_worker(profile_id: int) -> subprocess.Popen[str]:
        return subprocess.Popen(
            [sys.executable, "-m", "phantom.workers.main", "--profile-id", str(profile_id)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, text=True, bufsize=1,
            start_new_session=(os.name != "nt"),
        )

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        out["capabilities"] = json.loads(out.pop("capability_json") or "{}")
        out.pop("idempotency_key", None)
        out.pop("stop_idempotency_key", None)
        out.pop("user_data_dir", None)
        return out

    def _row(self, session_id: str, conn=None) -> dict[str, Any] | None:
        c = conn or db.get_conn()
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get(self, session_id: str) -> dict[str, Any]:
        with db.get_conn() as c:
            row = self._row(session_id, c)
        if not row:
            raise SessionNotFound(session_id)
        return self._public(row)

    def list(self) -> list[dict[str, Any]]:
        with db.get_conn() as c:
            rows = c.execute("SELECT * FROM sessions ORDER BY created_at, id").fetchall()
        return [self._public(dict(r)) for r in rows]

    def _event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            seq = c.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            c.execute(
                "INSERT INTO events(session_id,sequence,event_type,payload_json) VALUES(?,?,?,?)",
                (session_id, seq, event_type, json.dumps(payload, default=str)),
            )
        return int(seq)

    def events_after(self, session_id: str, sequence: int = 0) -> list[dict[str, Any]]:
        self.get(session_id)
        with db.get_conn() as c:
            rows = c.execute(
                "SELECT sequence,event_type,payload_json,created_at FROM events "
                "WHERE session_id=? AND sequence>? ORDER BY sequence", (session_id, sequence)
            ).fetchall()
        return [{"sequence": r["sequence"], "type": r["event_type"],
                 "data": json.loads(r["payload_json"]), "created_at": r["created_at"]}
                for r in rows]

    def start(self, profile_id: int, idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                old = c.execute("SELECT * FROM sessions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if old:
                    if old["profile_id"] != profile_id:
                        raise SessionConflict("idempotency key already used for another profile")
                    return self._public(dict(old)), False
            profile = c.execute("SELECT id,user_data_dir FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not profile:
                raise SessionNotFound(f"profile {profile_id}")
            existing = c.execute(
                "SELECT id FROM sessions WHERE profile_id=? AND status IN ('queued','starting','ready','stopping')",
                (profile_id,),
            ).fetchone()
            if existing:
                raise SessionConflict("profile already has an active session")
            active = c.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('starting','ready','stopping')").fetchone()[0]
            status = "starting" if active < self.max_concurrency else "queued"
            sid = str(uuid.uuid4())
            caps = {"transport": "actions", "actions": ["navigate", "snapshot", "screenshot", "cookies", "storage_state"]}
            c.execute(
                "INSERT INTO sessions(id,profile_id,status,user_data_dir,capability_json,idempotency_key) VALUES(?,?,?,?,?,?)",
                (sid, profile_id, status, profile["user_data_dir"], json.dumps(caps), idempotency_key),
            )
        self._event(sid, "session.queued" if status == "queued" else "session.starting", {"status": status})
        if status == "starting":
            self._launch(sid, profile_id)
        return self.get(sid), True

    def start_instant(self, profile_id: int, idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
        """Create an isolated disposable session while sharing the normal FIFO."""
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                old = c.execute("SELECT * FROM sessions WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if old:
                    if old["mode"] != "instant" or old["profile_id"] != profile_id:
                        raise SessionConflict("idempotency key already used for another request")
                    return self._public(dict(old)), False
            if not c.execute("SELECT id FROM profiles WHERE id=?", (profile_id,)).fetchone():
                raise SessionNotFound(f"profile {profile_id}")
            active = c.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('starting','ready','stopping')").fetchone()[0]
            state = "starting" if active < self.max_concurrency else "queued"
            sid = str(uuid.uuid4())
            temp_dir = paths.runtime_dir / "instant" / sid
            temp_dir.mkdir(parents=True, exist_ok=False)
            caps = {"transport": "actions", "actions": ["navigate", "snapshot", "screenshot", "cookies", "storage_state"]}
            c.execute("INSERT INTO sessions(id,profile_id,mode,status,user_data_dir,capability_json,idempotency_key) VALUES(?,?,?,?,?,?,?)",
                      (sid, profile_id, "instant", state, str(temp_dir), json.dumps(caps), idempotency_key))
        self._event(sid, "session.queued" if state == "queued" else "session.starting", {"status": state, "mode": "instant"})
        if state == "starting":
            self._launch(sid, profile_id)
        return self.get(sid), True

    def _cleanup_instant(self, sid: str) -> None:
        with db.get_conn() as c:
            row = self._row(sid, c)
        if row and row.get("mode") == "instant":
            root = (paths.runtime_dir / "instant").resolve()
            target = Path(row["user_data_dir"]).resolve()
            if root in target.parents:
                shutil.rmtree(target, ignore_errors=True)
            self._event(sid, "session.temp_cleaned", {"cleaned": not target.exists()})

    def _launch(self, sid: str, profile_id: int) -> None:
        try:
            proc = self._spawn(profile_id)
            with self._lock:
                self._processes[sid] = proc
                self._registry.register(profile_id, proc.pid, session_id=sid)
            with db.get_conn() as c:
                c.execute("UPDATE sessions SET worker_pid=?,updated_at=? WHERE id=?", (proc.pid, _utcnow(), sid))
            threading.Thread(target=self._monitor, args=(sid, profile_id, proc), daemon=True).start()
        except Exception as exc:
            self._set_status(sid, "crashed", exit_reason="spawn_failed")
            self._event(sid, "session.crashed", {"code": "SPAWN_FAILED", "message": str(exc)})
            self._cleanup_instant(sid)
            self._drain_queue()

    def _set_status(self, sid: str, status: str, *, exit_reason: str | None = None) -> None:
        stopped = _utcnow() if status in TERMINAL else None
        with db.get_conn() as c:
            c.execute("UPDATE sessions SET status=?,exit_reason=COALESCE(?,exit_reason),updated_at=?,"
                      "stopped_at=COALESCE(?,stopped_at) WHERE id=?",
                      (status, exit_reason, _utcnow(), stopped, sid))

    def _monitor(self, sid: str, profile_id: int, proc: subprocess.Popen[str]) -> None:
        try:
            if proc.stdout:
                for line in proc.stdout:
                    try:
                        raw = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        self._event(sid, "worker.protocol_error", {"message": "malformed worker event"})
                        continue
                    typ = raw.get("type")
                    if typ == "action_result" and raw.get("request_id"):
                        with self._action_condition:
                            self._action_results[str(raw["request_id"])] = raw
                            self._action_condition.notify_all()
                        continue
                    self._event(sid, f"worker.{typ or 'unknown'}", {"data": raw.get("data", {}), "error": raw.get("error")})
                    if typ == "ready":
                        self._set_status(sid, "ready")
                        self._registry.mark_ready(profile_id)
                        self._event(sid, "session.ready", {"status": "ready"})
            rc = proc.wait()
            current = self.get(sid)["status"]
            final = "stopped" if current == "stopping" else "crashed"
            self._set_status(sid, final, exit_reason="requested" if final == "stopped" else f"exit_{rc}")
            self._event(sid, f"session.{final}", {"status": final, "exit_code": rc})
            self._cleanup_instant(sid)
        finally:
            with self._lock:
                self._processes.pop(sid, None)
                self._registry.unregister(profile_id)
            self._drain_queue()

    def request_action(self, sid: str, action: str, args: dict[str, Any], *, timeout: float = 30.0) -> Any:
        """Send one JSON-line command to the owning worker and await its correlated result."""
        proc = self._processes.get(sid)
        if not proc or proc.poll() is not None or not proc.stdin:
            raise SessionConflict("worker action transport is unavailable")
        request_id = str(uuid.uuid4())
        try:
            proc.stdin.write(json.dumps({"type": "action", "request_id": request_id,
                                         "action": action, "args": args}) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise SessionConflict("worker action transport is unavailable") from exc
        import time
        deadline = time.monotonic() + timeout
        with self._action_condition:
            while request_id not in self._action_results:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("worker action timed out")
                self._action_condition.wait(remaining)
            raw = self._action_results.pop(request_id)
        if raw.get("error"):
            error = raw["error"]
            raise SessionConflict(error.get("message", "worker action failed"))
        return raw.get("data")

    def stop(self, sid: str, idempotency_key: str | None = None) -> tuple[dict[str, Any], bool]:
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = self._row(sid, c)
            if not row:
                raise SessionNotFound(sid)
            if idempotency_key and row.get("stop_idempotency_key") == idempotency_key:
                return self._public(row), False
            if row["stop_idempotency_key"] and idempotency_key and row["stop_idempotency_key"] != idempotency_key:
                raise SessionConflict("stop already requested with another idempotency key")
            if row["status"] in TERMINAL:
                return self._public(row), False
            if row["status"] == "queued":
                c.execute("UPDATE sessions SET status='stopped',stop_idempotency_key=?,stopped_at=?,updated_at=?,exit_reason='cancelled' WHERE id=?",
                          (idempotency_key, _utcnow(), _utcnow(), sid))
                queued = True
            else:
                c.execute("UPDATE sessions SET status='stopping',stop_idempotency_key=?,updated_at=? WHERE id=?",
                          (idempotency_key, _utcnow(), sid))
                queued = False
        self._event(sid, "session.stopped" if queued else "session.stopping", {"status": "stopped" if queued else "stopping"})
        if not queued:
            proc = self._processes.get(sid)
            if proc and proc.poll() is None:
                proc.terminate()
            elif row.get("worker_pid"):
                self._registry.stop_worker(row["profile_id"])
                self._set_status(sid, "stopped", exit_reason="requested")
            else:
                # No worker was ever attached (for example a spawn-less test
                # adapter); stopping is complete synchronously.
                self._set_status(sid, "stopped", exit_reason="requested")
                self._event(sid, "session.stopped", {"status": "stopped"})
        if queued or not self._processes.get(sid):
            self._cleanup_instant(sid)
        self._drain_queue()
        return self.get(sid), True

    def _drain_queue(self) -> None:
        with self._lock, db.get_conn() as c:
            active = c.execute("SELECT COUNT(*) FROM sessions WHERE status IN ('starting','ready','stopping')").fetchone()[0]
            slots = self.max_concurrency - active
            rows = c.execute("SELECT id,profile_id FROM sessions WHERE status='queued' ORDER BY created_at,id LIMIT ?", (max(0, slots),)).fetchall()
            for row in rows:
                c.execute("UPDATE sessions SET status='starting',updated_at=? WHERE id=? AND status='queued'", (_utcnow(), row["id"]))
        for row in rows:
            self._event(row["id"], "session.starting", {"status": "starting"})
            self._launch(row["id"], row["profile_id"])

    def reconcile(self) -> None:
        """After server restart no local handles exist: active rows are crashed; queued work resumes."""
        with db.get_conn() as c:
            rows = c.execute("SELECT id FROM sessions WHERE status IN ('starting','ready','stopping')").fetchall()
            for row in rows:
                c.execute("UPDATE sessions SET status='crashed',exit_reason='control_plane_restart',stopped_at=?,updated_at=? WHERE id=?",
                          (_utcnow(), _utcnow(), row["id"]))
        for row in rows:
            self._event(row["id"], "session.crashed", {"status": "crashed", "reason": "control_plane_restart"})
            self._cleanup_instant(row["id"])
        self._drain_queue()
