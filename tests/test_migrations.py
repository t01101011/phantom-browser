from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from phantom import db


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "phantom.db"
    os.environ["PHANTOM_DATA_DIR"] = str(tmp_path)
    yield db_path
    os.environ.pop("PHANTOM_DATA_DIR", None)


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


def test_empty_database_is_migrated_to_control_plane_schema(isolated_db):
    db.init_db()

    with db.get_conn() as conn:
        assert {
            "profiles",
            "running_instances",
            "folders",
            "proxies",
            "sessions",
            "session_leases",
            "events",
            "artifacts",
            "schema_migrations",
        } <= _tables(conn)
        profile_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()
        }
        assert {"folder_id", "proxy_id"} <= profile_columns
        assert [tuple(row) for row in conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()] == [(2,), (3,)]


def test_v1_database_migrates_without_losing_legacy_profile(isolated_db):
    schema = Path(db.SCHEMA_PATH).read_text()
    with sqlite3.connect(isolated_db) as conn:
        # A v1 fixture has the legacy tables but no migration ledger.
        legacy_schema = schema.split("CREATE TABLE IF NOT EXISTS schema_migrations")[0]
        conn.executescript(legacy_schema)
        conn.execute(
            """INSERT INTO profiles (
                name, platform_tag, proxy_host, proxy_port, proxy_user, proxy_pass,
                fingerprint_json, seeds_json, webgl_json, fonts_json, voices_json,
                misc_json, user_data_dir
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy",
                "facebook",
                "127.0.0.1",
                9000,
                "user",
                "secret",
                "{}",
                "{}",
                "{}",
                "[]",
                "[]",
                "{}",
                "/tmp/legacy",
            ),
        )

    db.init_db()

    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT name, proxy_pass, folder_id, proxy_id FROM profiles"
        ).fetchone()
        assert tuple(row) == ("legacy", "secret", None, None)
        assert [tuple(row) for row in conn.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()] == [(2,), (3,)]


def test_migrations_are_idempotent(isolated_db):
    db.init_db()
    with db.get_conn() as conn:
        before = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()

    db.init_db()

    with db.get_conn() as conn:
        after = conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        applied = conn.execute(
            "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version"
        ).fetchall()

    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    assert [tuple(row) for row in applied] == [(2, 1), (3, 1)]


def test_control_plane_indexes_cover_runtime_queries(isolated_db):
    db.init_db()

    with db.get_conn() as conn:
        assert {
            "idx_profiles_platform",
            "idx_profiles_status",
            "idx_profiles_proxy",
            "idx_profiles_folder",
            "idx_profiles_proxy_id",
            "idx_sessions_profile_status",
            "idx_sessions_status_created",
            "idx_session_leases_expires",
            "idx_events_session_created",
            "idx_artifacts_session_created",
        } <= _indexes(conn)


def test_proxy_usage_count_supports_v2_proxy_reference(isolated_db):
    db.init_db()
    with db.get_conn() as conn:
        proxy_id = conn.execute(
            "INSERT INTO proxies (name, host, port) VALUES (?, ?, ?)",
            ("residential-1", "198.51.100.7", 8080),
        ).lastrowid
        conn.execute(
            """INSERT INTO profiles (
                name, platform_tag, proxy_host, proxy_port, proxy_user, proxy_pass,
                fingerprint_json, seeds_json, webgl_json, fonts_json, voices_json,
                misc_json, user_data_dir, proxy_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "linked-v2", "facebook", "", 1, "", "", "{}", "{}",
                "{}", "[]", "[]", "{}", "/tmp/linked-v2", proxy_id,
            ),
        )

    assert db.proxy_usage_count("198.51.100.7", 8080) == 1


def test_sqlite_backup_restores_migrated_schema_and_data(isolated_db, tmp_path):
    db.init_db()
    with db.get_conn() as source:
        source.execute("INSERT INTO folders (name) VALUES ('Social')")
        source.commit()
        backup_path = tmp_path / "backup.db"
        with sqlite3.connect(backup_path) as backup:
            source.backup(backup)

    restored_path = tmp_path / "restored.db"
    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)

    with sqlite3.connect(restored_path) as conn:
        assert conn.execute("SELECT name FROM folders").fetchall() == [("Social",)]
        assert conn.execute("SELECT version FROM schema_migrations").fetchall() == [(2,), (3,)]
