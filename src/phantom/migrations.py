"""Versioned, additive SQLite migrations for Phantom Browser."""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )


def _migration_files() -> list[tuple[int, Path]]:
    migrations: list[tuple[int, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        migrations.append((int(path.name[:4]), path))
    return migrations


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply pending migrations atomically and return versions applied now."""
    _ensure_ledger(conn)
    applied = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    applied_now: list[int] = []

    for version, path in _migration_files():
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in _statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, path.name),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied_now.append(version)

    return applied_now


def _statements(sql: str) -> list[str]:
    """Split this project's migration SQL without using executescript commits."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer = f"{buffer}\n{line}" if buffer else line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError("incomplete migration SQL statement")
    return statements
