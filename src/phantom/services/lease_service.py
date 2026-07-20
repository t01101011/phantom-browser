"""Owner leases, TTL expiry, and safe artifact storage for agent sessions."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from phantom import db, paths
from phantom.services.session_service import SessionConflict, SessionNotFound

ARTIFACT_TYPES = {
    "screenshot": {"image/png", "image/jpeg"},
    "cookies": {"application/json"},
    "storage": {"application/json"},
}
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


class LeaseError(PermissionError):
    pass


class ArtifactError(ValueError):
    pass


def _real_utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class LeaseService:
    """Lease coordinator. Tokens are returned once; only SHA-256 hashes persist."""

    def __init__(self, session_service, *, clock: Callable[[], datetime] = _real_utcnow,
                 default_ttl: int = 60, max_ttl: int = 3600) -> None:
        self.sessions = session_service
        self.clock = clock
        self.default_ttl = default_ttl
        self.max_ttl = max_ttl
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._sweeper: threading.Thread | None = None
        # Viewer credentials stay in memory; restart invalidates takeover.
        self._takeovers: dict[str, dict[str, Any]] = {}
        self._snapshot_required: set[str] = set()

    def start_sweeper(self, interval: float = 1.0) -> None:
        """Start the control-plane TTL reaper (idempotent)."""
        if self._sweeper and self._sweeper.is_alive():
            return
        self._stop_event.clear()
        def run() -> None:
            while not self._stop_event.wait(interval):
                self.expire_due()
        self._sweeper = threading.Thread(target=run, name="phantom-lease-reaper", daemon=True)
        self._sweeper.start()

    def stop_sweeper(self) -> None:
        self._stop_event.set()
        if self._sweeper:
            self._sweeper.join(timeout=2)

    def _now(self) -> datetime:
        now = self.clock()
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _ttl(self, ttl_seconds: int | None) -> int:
        ttl = self.default_ttl if ttl_seconds is None else ttl_seconds
        if ttl < 1 or ttl > self.max_ttl:
            raise LeaseError(f"ttl_seconds must be between 1 and {self.max_ttl}")
        return ttl

    def acquire(self, session_id: str, *, ttl_seconds: int | None = None,
                owner_token: str | None = None) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if session["status"] in {"stopped", "crashed"}:
            raise LeaseError("cannot lease a terminal session")
        ttl = self._ttl(ttl_seconds)
        token = owner_token or secrets.token_urlsafe(32)
        now = self._now()
        expires = now + timedelta(seconds=ttl)
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM session_leases WHERE session_id=?", (session_id,)).fetchone()
            if row and _parse(row["lease_expires_at"]) > now:
                raise LeaseError("session already has an active lease")
            generation = (int(row["generation"]) + 1) if row else 1
            c.execute(
                "INSERT INTO session_leases(session_id,owner_token_hash,generation,lease_expires_at,heartbeat_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET owner_token_hash=excluded.owner_token_hash,"
                "generation=excluded.generation,lease_expires_at=excluded.lease_expires_at,heartbeat_at=excluded.heartbeat_at",
                (session_id, self._hash(token), generation, expires.isoformat(), now.isoformat()),
            )
        self.sessions._event(session_id, "lease.acquired", {"generation": generation, "expires_at": expires.isoformat()})
        return {"session_id": session_id, "owner_token": token, "generation": generation,
                "lease_expires_at": expires.isoformat()}

    def heartbeat(self, session_id: str, token: str, generation: int,
                  *, ttl_seconds: int | None = None) -> dict[str, Any]:
        ttl = self._ttl(ttl_seconds)
        now = self._now()
        expires = now + timedelta(seconds=ttl)
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM session_leases WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                raise SessionNotFound("lease")
            if not secrets.compare_digest(row["owner_token_hash"], self._hash(token)) or int(row["generation"]) != generation:
                raise LeaseError("lease owner or generation mismatch")
            old_expires = _parse(row["lease_expires_at"])
            if old_expires <= now:
                raise LeaseError("lease expired")
            expires = max(expires, old_expires)
            c.execute("UPDATE session_leases SET lease_expires_at=?,heartbeat_at=? WHERE session_id=?",
                      (expires.isoformat(), now.isoformat(), session_id))
        self.sessions._event(session_id, "lease.heartbeat", {"generation": generation, "expires_at": expires.isoformat()})
        return {"session_id": session_id, "generation": generation, "lease_expires_at": expires.isoformat()}

    def release(self, session_id: str, token: str, generation: int) -> bool:
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM session_leases WHERE session_id=?", (session_id,)).fetchone()
            if not row:
                return False
            if not secrets.compare_digest(row["owner_token_hash"], self._hash(token)) or int(row["generation"]) != generation:
                raise LeaseError("lease owner or generation mismatch")
            c.execute("DELETE FROM session_leases WHERE session_id=?", (session_id,))
        self.sessions._event(session_id, "lease.released", {"generation": generation})
        return True

    def takeover_active(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._takeovers

    def snapshot_required(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._snapshot_required

    def snapshot_refreshed(self, session_id: str) -> None:
        with self._lock:
            self._snapshot_required.discard(session_id)

    def begin_takeover(self, session_id: str, token: str, generation: int) -> dict[str, Any]:
        """Revoke agent input and grant a human controlling the same X display."""
        self.sessions.get(session_id)
        now = self._now()
        takeover_token = secrets.token_urlsafe(32)
        with self._lock, db.get_conn() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM session_leases WHERE session_id=?", (session_id,)).fetchone()
            if not row or _parse(row["lease_expires_at"]) <= now:
                raise LeaseError("active agent lease required")
            if int(row["generation"]) != generation or not secrets.compare_digest(row["owner_token_hash"], self._hash(token)):
                raise LeaseError("lease owner or generation mismatch")
            human_generation = generation + 1
            expires = now + timedelta(seconds=self.max_ttl)
            c.execute("UPDATE session_leases SET owner_token_hash=?,generation=?,lease_expires_at=?,heartbeat_at=? WHERE session_id=?",
                      (self._hash(takeover_token), human_generation, expires.isoformat(), now.isoformat(), session_id))
            self._takeovers[session_id] = {"token_hash": self._hash(takeover_token), "generation": human_generation}
        self.sessions._event(session_id, "takeover.started", {"generation": human_generation})
        return {"session_id": session_id, "takeover_token": takeover_token,
                "generation": human_generation, "lease_expires_at": expires.isoformat()}

    def end_takeover(self, session_id: str, takeover_token: str) -> dict[str, Any]:
        """Release the human and issue a fresh agent lease/snapshot boundary."""
        now = self._now()
        agent_token = secrets.token_urlsafe(32)
        with self._lock, db.get_conn() as c:
            state = self._takeovers.get(session_id)
            if not state or not secrets.compare_digest(state["token_hash"], self._hash(takeover_token)):
                raise LeaseError("takeover owner mismatch")
            generation = int(state["generation"]) + 1
            expires = now + timedelta(seconds=self.default_ttl)
            c.execute("UPDATE session_leases SET owner_token_hash=?,generation=?,lease_expires_at=?,heartbeat_at=? WHERE session_id=?",
                      (self._hash(agent_token), generation, expires.isoformat(), now.isoformat(), session_id))
            del self._takeovers[session_id]
            self._snapshot_required.add(session_id)
        self.sessions._event(session_id, "takeover.released", {"generation": generation, "fresh_snapshot_required": True})
        return {"session_id": session_id, "owner_token": agent_token, "generation": generation,
                "lease_expires_at": expires.isoformat(), "fresh_snapshot_required": True}

    def expire_due(self) -> list[str]:
        now = self._now()
        with db.get_conn() as c:
            rows = c.execute("SELECT l.session_id FROM session_leases l JOIN sessions s ON s.id=l.session_id "
                             "WHERE l.lease_expires_at<=? AND s.status NOT IN ('stopped','crashed')",
                             (now.isoformat(),)).fetchall()
        expired: list[str] = []
        for row in rows:
            sid = row["session_id"]
            try:
                self.sessions._event(sid, "lease.expired", {"expired_at": now.isoformat()})
                self.sessions.stop(sid, f"ttl:{sid}")
                expired.append(sid)
            except (SessionNotFound, SessionConflict):
                pass
        return expired


class ArtifactService:
    """Artifact metadata and bytes, rooted below PHANTOM_DATA_DIR/artifacts."""

    def __init__(self, sessions, *, max_bytes: int = MAX_ARTIFACT_BYTES,
                 clock: Callable[[], datetime] = _real_utcnow) -> None:
        self.sessions = sessions
        self.max_bytes = max_bytes
        self.clock = clock

    def _root(self) -> Path:
        root = paths.artifacts_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def put(self, session_id: str, artifact_type: str, content_type: str, data: bytes,
            *, retention_seconds: int = 86400) -> dict[str, Any]:
        self.sessions.get(session_id)
        allowed = ARTIFACT_TYPES.get(artifact_type)
        if not allowed or content_type not in allowed:
            raise ArtifactError("unsupported artifact type or content type")
        if len(data) > self.max_bytes:
            raise ArtifactError("artifact exceeds size limit")
        if retention_seconds < 1:
            raise ArtifactError("retention_seconds must be positive")
        if artifact_type in {"cookies", "storage"}:
            try:
                parsed = json.loads(data)
            except Exception as exc:
                raise ArtifactError("JSON artifact is invalid") from exc
            # Never persist common credential-bearing fields in exported state.
            def redact(value):
                if isinstance(value, dict):
                    return {k: ("*****" if any(x in k.lower() for x in ("password", "token", "secret", "authorization")) else redact(v)) for k, v in value.items()}
                if isinstance(value, list):
                    return [redact(v) for v in value]
                return value
            data = json.dumps(redact(parsed), separators=(",", ":")).encode()
        aid = str(uuid.uuid4())
        ext = ".json" if content_type == "application/json" else (mimetypes.guess_extension(content_type) or ".bin")
        directory = (self._root() / session_id).resolve()
        if self._root() not in directory.parents:
            raise ArtifactError("invalid session path")
        directory.mkdir(parents=True, exist_ok=True)
        target = (directory / f"{aid}{ext}").resolve()
        if directory not in target.parents:
            raise ArtifactError("invalid artifact path")
        target.write_bytes(data)
        checksum = hashlib.sha256(data).hexdigest()
        now = self.clock()
        expires = now + timedelta(seconds=retention_seconds)
        with db.get_conn() as c:
            c.execute("INSERT INTO artifacts(id,session_id,artifact_type,path,content_type,size_bytes,checksum_sha256,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                      (aid, session_id, artifact_type, str(target.relative_to(self._root())), content_type, len(data), checksum, expires.isoformat()))
        self.sessions._event(session_id, "artifact.created", {"artifact_id": aid, "type": artifact_type, "size_bytes": len(data)})
        return self.get(aid)[0]

    def get(self, artifact_id: str) -> tuple[dict[str, Any], Path]:
        with db.get_conn() as c:
            row = c.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if not row:
            raise SessionNotFound("artifact")
        meta = dict(row)
        candidate = (self._root() / meta.pop("path")).resolve()
        if self._root() not in candidate.parents or not candidate.is_file():
            raise ArtifactError("artifact path is unsafe or missing")
        return meta, candidate

    def list(self, session_id: str) -> list[dict[str, Any]]:
        self.sessions.get(session_id)
        with db.get_conn() as c:
            rows = c.execute("SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at,id", (session_id,)).fetchall()
        return [{k: v for k, v in dict(r).items() if k != "path"} for r in rows]

    def cleanup_expired(self) -> int:
        now = self.clock().isoformat()
        with db.get_conn() as c:
            rows = c.execute("SELECT id FROM artifacts WHERE expires_at IS NOT NULL AND expires_at<=?", (now,)).fetchall()
        count = 0
        for row in rows:
            try:
                _, path = self.get(row["id"])
                path.unlink(missing_ok=True)
            except (SessionNotFound, ArtifactError):
                pass
            with db.get_conn() as c:
                c.execute("DELETE FROM artifacts WHERE id=?", (row["id"],))
            count += 1
        return count
