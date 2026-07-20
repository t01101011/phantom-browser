from __future__ import annotations

import json
import os

import pytest

from phantom import db, identity


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    os.environ["PHANTOM_DATA_DIR"] = str(tmp_path)
    db.init_db()
    yield
    os.environ.pop("PHANTOM_DATA_DIR", None)


def test_reconstructed_identity_builds_byte_identical_launch_config(isolated_db):
    blobs = identity.generate_identity("windows")
    profile = {
        **blobs,
        "timezone": "America/Denver",
        "locale_language": "en",
        "locale_region": "US",
        "navigator_language": "en-US",
    }

    first_fp, first_config = identity.build_launch_config(profile)
    second_fp, second_config = identity.build_launch_config(profile)

    assert first_fp.dumps() == second_fp.dumps()
    assert json.dumps(first_config, sort_keys=True, default=str) == json.dumps(
        second_config, sort_keys=True, default=str
    )
    assert first_config["timezone"] == "America/Denver"
    assert first_config["navigator.languages"] == ["en-US"]
