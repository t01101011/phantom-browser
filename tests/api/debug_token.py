"""Debug — figure out why token auth is failing."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi.testclient import TestClient

from phantom.api.app import create_app
from phantom.api.auth import load_or_generate_token
from phantom.paths import runtime_dir


def test_debug_token(tmp_path: Path) -> None:
    data_dir = tmp_path / "debug_data"
    (data_dir / "runtime").mkdir(parents=True, exist_ok=True)

    # Write a known token
    expected_token = "my-test-token-value-for-debugging-purposes"
    (data_dir / "runtime" / ".api_token").write_text(expected_token)

    # Set env var
    os.environ["PHANTOM_DATA_DIR"] = str(data_dir)

    # Check what paths resolves to
    from phantom import paths
    print(f"DEBUG: paths.data_dir = {paths.data_dir}")
    print(f"DEBUG: paths.runtime_dir = {paths.runtime_dir}")
    print(f"DEBUG: env PHANTOM_DATA_DIR = {os.environ.get('PHANTOM_DATA_DIR')}")
    print(f"DEBUG: expected token path = {paths.runtime_dir / '.api_token'}")
    print(f"DEBUG: exists = {(paths.runtime_dir / '.api_token').exists()}")

    # Load token
    loaded = load_or_generate_token()
    print(f"DEBUG: loaded token = '{loaded}'")
    print(f"DEBUG: expected token = '{expected_token}'")
    print(f"DEBUG: match = {loaded == expected_token}")

    # Now with app
    app = create_app()
    client = TestClient(app)

    resp = client.get(
        "/readyz",
        headers={"Authorization": f"Bearer {expected_token}"},
    )
    print(f"DEBUG: resp status = {resp.status_code}")
    print(f"DEBUG: resp body = {resp.json()}")

    os.environ.pop("PHANTOM_DATA_DIR", None)
