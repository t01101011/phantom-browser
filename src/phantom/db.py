"""SQLite layer — sqlite3 stdlib, no ORM.

Single-file DB at ``paths.db_path`` (platformdirs user_data_dir by default,
overridable via ``PHANTOM_DATA_DIR``).  WAL mode for concurrent read+launch.
Connection helper returns a row factory (dict) for ergonomics.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Optional

from . import migrations, paths

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def DB_PATH() -> Path:
    """Resolve DB path dynamically so PHANTOM_DATA_DIR changes are picked up."""
    return paths.db_path


def get_conn() -> sqlite3.Connection:
    """Return a connection with WAL + foreign keys + dict rows."""
    dbp = paths.db_path
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create the legacy-compatible base schema, then apply pending migrations."""
    with get_conn() as c:
        c.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrations.apply_migrations(c)


# --- CRUD ---------------------------------------------------------------------

def create_profile(row: dict, conn: Optional[sqlite3.Connection] = None) -> int:
    cols = ", ".join(row.keys())
    phs = ", ".join(["?"] * len(row))
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            cur = c.execute(f"INSERT INTO profiles ({cols}) VALUES ({phs})", list(row.values()))
            return cur.lastrowid
    else:
        cur = c.execute(f"INSERT INTO profiles ({cols}) VALUES ({phs})", list(row.values()))
        return cur.lastrowid


def get_profile(profile_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            r = c.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            return dict(r) if r else None
    else:
        r = c.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return dict(r) if r else None


def get_profile_by_name(name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            r = c.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
            return dict(r) if r else None
    else:
        r = c.execute("SELECT * FROM profiles WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None


def list_profiles(platform_tag: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            if platform_tag:
                rows = c.execute(
                    "SELECT * FROM profiles WHERE platform_tag=? ORDER BY id", (platform_tag,)
                ).fetchall()
            else:
                rows = c.execute("SELECT * FROM profiles ORDER BY id").fetchall()
            return [dict(r) for r in rows]
    else:
        if platform_tag:
            rows = c.execute(
                "SELECT * FROM profiles WHERE platform_tag=? ORDER BY id", (platform_tag,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM profiles ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def list_profiles_by_status(status: str, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """List profiles with a given status (running, idle, crashed, etc.)."""
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            rows = c.execute(
                "SELECT * FROM profiles WHERE status=? ORDER BY id", (status,)
            ).fetchall()
            return [dict(r) for r in rows]
    else:
        rows = c.execute(
            "SELECT * FROM profiles WHERE status=? ORDER BY id", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_profile(profile_id: int, fields: dict, conn: Optional[sqlite3.Connection] = None) -> int:
    if not fields:
        return 0
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [profile_id]
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            cur = c.execute(
                f"UPDATE profiles SET {sets}, updated_at=datetime('now') WHERE id=?", vals
            )
            return cur.rowcount
    else:
        cur = c.execute(
            f"UPDATE profiles SET {sets}, updated_at=datetime('now') WHERE id=?", vals
        )
        return cur.rowcount


def delete_profile(profile_id: int, conn: Optional[sqlite3.Connection] = None) -> int:
    c = conn if conn is not None else get_conn()
    if conn is None:
        with c:
            cur = c.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
            return cur.rowcount
    else:
        cur = c.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        return cur.rowcount


def set_status(profile_id: int, status: str) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE profiles SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, profile_id),
        )


# --- Running instances --------------------------------------------------------

def mark_running(profile_id: int, pid: int) -> None:
    with get_conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO running_instances (profile_id, pid) VALUES (?, ?)",
            (profile_id, pid),
        )


def mark_stopped(profile_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM running_instances WHERE profile_id=?", (profile_id,))


def is_running(profile_id: int) -> Optional[int]:
    """Return PID if running, else None."""
    with get_conn() as c:
        r = c.execute(
            "SELECT pid FROM running_instances WHERE profile_id=?", (profile_id,)
        ).fetchone()
        return r["pid"] if r else None


def proxy_usage_count(host: str, port: int, exclude_profile_id: Optional[int] = None) -> int:
    """Count profiles using a legacy inline proxy or a v2 proxy reference."""
    query = """
        SELECT COUNT(DISTINCT p.id) AS n
        FROM profiles AS p
        LEFT JOIN proxies AS x ON x.id = p.proxy_id
        WHERE ((p.proxy_host=? AND p.proxy_port=?) OR (x.host=? AND x.port=?))
    """
    params: list[Any] = [host, port, host, port]
    if exclude_profile_id is not None:
        query += " AND p.id!=?"
        params.append(exclude_profile_id)
    with get_conn() as c:
        r = c.execute(query, params).fetchone()
        return r["n"] if r else 0
