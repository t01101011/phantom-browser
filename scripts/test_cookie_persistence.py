#!/usr/bin/env python3
"""Cookie/session persistence test for Phase 2 blocker.

Verifies that Camoufox persistent_context=True + user_data_dir survives
across two launches of the same profile.

Flow:
  1. Launch profile with persistent=True, headless='virtual'.
  2. Navigate to a page, set a uniquely-named cookie (marker).
  3. Read it back, confirm set. Close browser.
  4. Re-launch the SAME profile (same user_data_dir).
  5. Open a same-origin page WITHOUT setting the cookie.
  6. Read document.cookie — marker MUST be present.

If marker survives, persistent_context is working: cookies + localStorage
persist in user_data_dir across launches. This is the foundation for
"keep logged in across launches" in the GUI.

Run from repo root with venv active:
    set -a && . .env && set +a
    .venv/bin/python scripts/test_cookie_persistence.py 1
"""
from __future__ import annotations
import sys
import time
import uuid
from pathlib import Path

# Allow running as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom import db, launcher  # noqa: E402


def _set_marker_and_get(page, marker: str, origin: str) -> dict:
    """Set the marker cookie at origin, then read it back."""
    page.goto(origin, timeout=30000, wait_until="domcontentloaded")
    # set cookie via document.cookie (browser-accessible)
    page.evaluate(
        "(m) => { document.cookie = 'phantom_marker=' + m + '; path=/; SameSite=Lax; max-age=3600'; }",
        marker,
    )
    cookie = page.evaluate("() => document.cookie")
    return {"set_cookie_result": cookie}


def _read_marker(page, origin: str) -> dict:
    """Open origin WITHOUT setting cookie — should already be there."""
    page.goto(origin, timeout=30000, wait_until="domcontentloaded")
    return {"persisted_cookie": page.evaluate("() => document.cookie")}


def run(profile_id: int) -> int:
    db.init_db()
    profile = db.get_profile(profile_id)
    if profile is None:
        print(f"[!] profile {profile_id} not found")
        return 2

    marker = f"persist-{uuid.uuid4().hex[:12]}"
    origin = "https://example.com"   # stable, no login wall, sets document.cookie

    from camoufox.sync_api import Camoufox
    from phantom.identity import build_launch_config

    # Clean any stale running entry first
    db.mark_stopped(profile_id)
    db.set_status(profile_id, "idle")

    udd = launcher._ensure_user_data_dir(profile_id)
    db.update_profile(profile_id, {"user_data_dir": str(udd)})

    print(f"[*] profile {profile_id} ({profile['name']})")
    print(f"[*] user_data_dir: {udd}")
    print(f"[*] marker cookie: {marker}")
    print()

    # ----- Launch 1: set marker -----
    print("[1] Launch #1 — set marker cookie …")
    fp_obj, config = build_launch_config(profile)
    db.set_status(profile_id, "running")
    db.mark_running(profile_id, __import__("os").getpid())
    try:
        with Camoufox(
            headless="virtual",
            fingerprint=fp_obj,
            i_know_what_im_doing=True,
            proxy=launcher._proxy_dict(profile),
            geoip=True,
            block_webrtc=True,
            config=config,
            debug=False,
            persistent_context=True,
            user_data_dir=str(udd),
        ) as browser:
            context = browser  # persistent_context returns a BrowserContext
            page = context.new_page()
            res1 = _set_marker_and_get(page, marker, origin)
            print(f"    set result: {res1['set_cookie_result']}")
            assert marker in res1["set_cookie_result"], "marker not set on launch 1!"
            print("    [OK] marker set")
            # Close context explicitly so profile dir flush is clean
            context.close()
    finally:
        db.mark_stopped(profile_id)
        db.set_status(profile_id, "idle")
    print()

    # Give the profile dir a beat to flush to disk
    time.sleep(2)

    # ----- Launch 2: read marker (without setting) -----
    print("[2] Launch #2 — read marker cookie (should persist) …")
    fp_obj, config = build_launch_config(profile)
    db.set_status(profile_id, "running")
    db.mark_running(profile_id, __import__("os").getpid())
    try:
        with Camoufox(
            headless="virtual",
            fingerprint=fp_obj,
            i_know_what_im_doing=True,
            proxy=launcher._proxy_dict(profile),
            geoip=True,
            block_webrtc=True,
            config=config,
            debug=False,
            persistent_context=True,
            user_data_dir=str(udd),
        ) as browser:
            page = browser.new_page()
            res2 = _read_marker(page, origin)
            print(f"    persisted: {res2['persisted_cookie']}")
    finally:
        db.mark_stopped(profile_id)
        db.set_status(profile_id, "idle")
    print()

    if marker in (res2.get("persisted_cookie") or ""):
        print(f"[PASS] marker cookie '{marker}' survived across launches.")
        print("      → persistent_context + user_data_dir is working.")
        return 0
    else:
        print(f"[FAIL] marker cookie '{marker}' did NOT survive.")
        print(f"       got: {res2.get('persisted_cookie')!r}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(int(sys.argv[1])))
