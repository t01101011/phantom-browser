from __future__ import annotations

import os
import sqlite3

import pytest

from phantom import db


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "profiles.db"
    os.environ["PHANTOM_DATA_DIR"] = str(tmp_path)
    db.init_db()
    yield db_path
    os.environ.pop("PHANTOM_DATA_DIR", None)


@pytest.fixture()
def profile_row():
    return {
        "name": "alpha",
        "platform_tag": "facebook",
        "proxy_host": "127.0.0.1",
        "proxy_port": 9000,
        "proxy_user": "user",
        "proxy_pass": "secret",
        "fingerprint_json": "{}",
        "seeds_json": "{}",
        "webgl_json": "{}",
        "fonts_json": "[]",
        "voices_json": "[]",
        "misc_json": "{}",
        "user_data_dir": "",
    }


def test_profile_crud_and_running_cleanup(isolated_db, profile_row):
    profile_id = db.create_profile(profile_row)

    assert db.get_profile(profile_id)["name"] == "alpha"
    assert db.get_profile_by_name("alpha")["id"] == profile_id
    assert [row["id"] for row in db.list_profiles()] == [profile_id]

    assert db.update_profile(profile_id, {"notes": "updated"}) == 1
    assert db.get_profile(profile_id)["notes"] == "updated"

    db.mark_running(profile_id, 4242)
    assert db.is_running(profile_id) == 4242

    assert db.delete_profile(profile_id) == 1
    assert db.get_profile(profile_id) is None
    assert db.is_running(profile_id) is None


def test_connections_enable_wal_and_foreign_keys(isolated_db):
    with db.get_conn() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1


def test_running_instance_requires_existing_profile(isolated_db):
    with pytest.raises(sqlite3.IntegrityError):
        db.mark_running(999, 4242)
