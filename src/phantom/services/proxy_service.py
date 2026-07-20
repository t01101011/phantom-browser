"""Proxy service — transaction-safe proxy CRUD and health checking.

Every public function takes an optional ``conn`` kwarg so callers can
share a transaction.  When ``conn`` is omitted a fresh connection is
acquired (auto-commit).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from phantom import db
from phantom.settings import redact_dict


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_conn(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    return conn if conn is not None else db.get_conn()


def _public_proxy(row: Optional[dict]) -> Optional[dict]:
    """Strip password from a proxy row for API responses."""
    if row is None:
        return None
    return {k: ("*****" if k == "password" else v) for k, v in row.items()}


def _execute_in_conn(
    conn: Optional[sqlite3.Connection],
    callback,
):
    """Run *callback(c)* with a connection, closing it if we opened it."""
    c = _get_conn(conn)
    if conn is None:
        with c:
            return callback(c)
    else:
        return callback(c)


# ── CRUD ───────────────────────────────────────────────────────────────────────


def create_proxy(
    name: str,
    scheme: str = "http",
    host: str = "",
    port: int = 1080,
    username: str = "",
    password: str = "",
    source: str = "manual",
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """Create a new proxy entry.

    Returns the created proxy dict (password redacted).
    Raises ``ValueError`` on duplicate name or invalid args.
    """
    if not host:
        raise ValueError("host is required")
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    if scheme not in ("http", "https", "socks4", "socks5"):
        raise ValueError(f"unsupported scheme: {scheme!r}")

    def _work(c):
        existing = c.execute(
            "SELECT id FROM proxies WHERE name=?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Proxy name '{name}' already exists")

        cur = c.execute(
            """INSERT INTO proxies (name, scheme, host, port, username, password, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, scheme, host, port, username, password, source),
        )
        new_id = cur.lastrowid
        return _public_proxy(dict(
            c.execute("SELECT * FROM proxies WHERE id=?", (new_id,)).fetchone()
        ))

    return _execute_in_conn(conn, _work)


def get_proxy(proxy_id: int, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    """Return a proxy row (password redacted) or None."""
    def _work(c):
        row = c.execute("SELECT * FROM proxies WHERE id=?", (proxy_id,)).fetchone()
        return _public_proxy(dict(row) if row else None)

    return _execute_in_conn(conn, _work)


def list_proxies(conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """List all proxies (passwords redacted)."""
    def _work(c):
        rows = c.execute("SELECT * FROM proxies ORDER BY name").fetchall()
        return [_public_proxy(dict(r)) for r in rows]

    return _execute_in_conn(conn, _work)


def update_proxy(
    proxy_id: int,
    fields: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Update proxy fields.  Returns updated proxy or None if not found."""
    allowed = {"name", "scheme", "host", "port", "username", "password", "source"}
    given = {k: v for k, v in fields.items() if k in allowed}
    if not given:
        raise ValueError("No valid fields to update")

    def _work(c):
        existing = c.execute(
            "SELECT id FROM proxies WHERE id=?", (proxy_id,)
        ).fetchone()
        if not existing:
            return None

        # Check name uniqueness
        if "name" in given:
            dup = c.execute(
                "SELECT id FROM proxies WHERE name=? AND id!=?",
                (given["name"], proxy_id),
            ).fetchone()
            if dup:
                raise ValueError(f"Proxy name '{given['name']}' already exists")

        sets = ", ".join(f"{k}=?" for k in given)
        vals = list(given.values()) + [proxy_id]
        c.execute(
            f"UPDATE proxies SET {sets}, updated_at=datetime('now') WHERE id=?",
            vals,
        )
        updated = dict(
            c.execute("SELECT * FROM proxies WHERE id=?", (proxy_id,)).fetchone()
        )
        return _public_proxy(updated)

    return _execute_in_conn(conn, _work)


def delete_proxy(proxy_id: int, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Delete a proxy.  Refuses if referenced by any profile."""
    def _work(c):
        ref_count = c.execute(
            "SELECT COUNT(*) AS n FROM profiles WHERE proxy_id=?", (proxy_id,)
        ).fetchone()["n"]
        if ref_count > 0:
            raise RuntimeError(
                f"Cannot delete proxy {proxy_id}: {ref_count} profile(s) reference it"
            )

        cur = c.execute("DELETE FROM proxies WHERE id=?", (proxy_id,))
        return cur.rowcount > 0

    return _execute_in_conn(conn, _work)


# ── Health check ───────────────────────────────────────────────────────────────


def check_proxy_health(proxy_id: int) -> dict:
    """Run a structured health check on a proxy.

    Returns ``{"proxy_id", "status", "latency_ms", "exit_ip", "error"?}``.
    Does NOT log or return credentials.
    """
    proxy = get_proxy(proxy_id)
    if proxy is None:
        raise ValueError(f"Proxy {proxy_id} not found")

    # Fetch full row for credentials (get_proxy redacts password)
    with db.get_conn() as c:
        full = dict(
            c.execute("SELECT * FROM proxies WHERE id=?", (proxy_id,)).fetchone()
        )

    import time
    import urllib.request

    host = full["host"]
    port = full["port"]
    username = full.get("username", "")
    password = full.get("password", "")

    proxy_url = f"{full['scheme']}://"
    if username and password:
        import urllib.parse
        proxy_url += f"{urllib.parse.quote(username)}:{urllib.parse.quote(password)}@"
    proxy_url += f"{host}:{port}"

    start = time.monotonic()
    try:
        handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        })
        opener = urllib.request.build_opener(handler)

        resp = opener.open("http://httpbin.org/ip", timeout=15)
        elapsed = (time.monotonic() - start) * 1000  # ms
        body = resp.read().decode()

        import json
        data = json.loads(body)
        exit_ip = data.get("origin", "unknown")

        # Update health status in DB
        with db.get_conn() as c2:
            c2.execute(
                """UPDATE proxies
                   SET health_status=?, last_checked_at=datetime('now')
                   WHERE id=?""",
                ("ok", proxy_id),
            )

        return {
            "proxy_id": proxy_id,
            "status": "ok",
            "latency_ms": round(elapsed, 1),
            "exit_ip": exit_ip,
        }
    except Exception as exc:
        # Update health status to error
        with db.get_conn() as c2:
            c2.execute(
                """UPDATE proxies
                   SET health_status=?, last_checked_at=datetime('now')
                   WHERE id=?""",
                ("error", proxy_id),
            )

        return {
            "proxy_id": proxy_id,
            "status": "error",
            "error": str(exc),
        }
