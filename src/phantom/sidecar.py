"""phantom.sidecar — JSON-RPC-over-stdio layer for the Tauri GUI.

Why a sidecar instead of `cli.py --json`?
  - `cli.py` is the human CLI (text output, sys.exit on errors). Retrofitting
    a `--json` flag would complicate every command and risk breaking the
    terminal UX that tk already uses. Keep them separate.
  - The sidecar is JSON-only: every command exits 0 and prints a JSON envelope
    `{ok: true, data: ...}` / `{ok: false, error: {code, message, detail?}}`.
    The Tauri Rust layer spawns this and parses one JSON object per call.

Contract (stable across dev + ship):
  Dev:  `python -m phantom.sidecar <action> [--args...]`
  Ship: `phantom-sidecar.exe <action> [--args...]`  (PyInstaller-bundled)
  stdout = ONE JSON object. stderr = diagnostic logs only (never parsed).
  exit code = 0 even on logical errors (so Rust can `serde_json` the body);
              only non-zero on stdlib crash (e.g. arg parse panic) — Rust
              should still attempt to read stdout for an envelope.

Actions:
  list                                → all profiles (lightweight)
  get           <id|name>             → profile detail (no secrets)
  create        --name --platform --proxy [--tz --notes]   → new profile
  launch        <id|name> [--url] [--headless H]            → detached launch, returns pid
  stop          <id|name>                                    → stop running browser
  delete        <id|name>                                    → delete profile (refuses if running)
  status        <id|name>                                   → {running, pid, status, log_path}
  log-tail      <id|name> [--bytes N]                       → last N bytes of launcher.log
  presets                                                        → list of platform presets

Phase 2 will add a long-lived streaming log-tail mode (HTTP SSE) when needed;
for now the GUI polls `log-tail` every ~1s while a profile is running.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from . import paths

# Load .env so PROXY_* are visible without an extra step (matches cli.py behaviour)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
if ENV_PATH.exists():
    for _line in ENV_PATH.read_text().splitlines():
        if "=" in _line and not _line.strip().startswith("#"):
            _k, _v = _line.split("=", 1)
            import os
            os.environ.setdefault(_k, _v.strip())


# --- Error type --------------------------------------------------------------

class SidecarError(Exception):
    """A user-facing sidecar error. Maps to a stable `code` string."""
    def __init__(self, code: str, message: str, detail: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


# --- Output helper -----------------------------------------------------------

def _emit(ok: bool, data: Any = None, *,
          error: Optional[dict] = None) -> None:
    """Print exactly one JSON object to stdout and flush."""
    payload = {"ok": ok}
    if ok:
        payload["data"] = data
    else:
        payload["error"] = error or {"code": "unknown", "message": "unknown"}
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


# --- Profile row sanitiser ---------------------------------------------------

_SECRET_FIELDS = (
    "proxy_pass", "fingerprint_json", "seeds_json",
    "webgl_json", "fonts_json", "voices_json", "misc_json",
)


def _public_profile(row: dict) -> dict:
    """Strip secrets + blob blobs from a profile row for GUI rendering.

    The GUI only needs display fields. Detail queries (fingerprint_viewer)
    can opt in to the full blobs later via a separate action.
    """
    return {k: v for k, v in row.items() if k not in _SECRET_FIELDS}


# --- Action handlers ---------------------------------------------------------

def _resolve_profile(arg: str) -> int:
    """`42` → int id; `name-string` → lookup; raises SidecarError on miss."""
    from . import db
    if arg.isdigit():
        return int(arg)
    row = db.get_profile_by_name(arg)
    if row is None:
        raise SidecarError("not_found", f"profile {arg!r} not found")
    return row["id"]


def action_list(args) -> Any:
    from . import db
    db.init_db()
    rows = db.list_profiles(args.platform)
    return {
        "profiles": [_public_profile(r) for r in rows],
        "count": len(rows),
    }


def action_get(args) -> Any:
    from . import db
    db.init_db()
    pid = _resolve_profile(args.profile)
    row = db.get_profile(pid)
    if row is None:
        raise SidecarError("not_found", f"profile {pid} not found")
    return _public_profile(row)


def action_create(args) -> Any:
    from . import db, identity, presets
    db.init_db()
    preset = presets.get_preset(args.platform)

    try:
        host, port, user, pw = args.proxy.split(":", 3)
        proxy_host, proxy_port = host, int(port)
    except (ValueError, AttributeError):
        raise SidecarError(
            "bad_proxy",
            "--proxy must be 'host:port:user:pass' (pass may contain colons)",
        )

    dup = db.proxy_usage_count(proxy_host, proxy_port)
    blobs = identity.generate_identity(target_os=preset["target_os"])
    tz = args.tz or preset.get("timezone_default")

    row = {
        "name":               args.name,
        "platform_tag":       preset["platform_tag"],
        "target_os":          preset["target_os"],
        "proxy_host":         proxy_host,
        "proxy_port":         proxy_port,
        "proxy_user":         user,
        "proxy_pass":         pw,
        "proxy_source":       "manual",
        "timezone":           tz,
        "locale_language":    "en",
        "locale_region":      preset["locale_region"],
        "navigator_language": preset["navigator_language"],
        "user_data_dir":     "",
        "notes":              args.notes or preset.get("notes_default", ""),
        **blobs,
    }
    pid = db.create_profile(row)
    created = db.get_profile(pid)
    return {
        "profile": _public_profile(created),
        "duplicate_proxy_count": dup,   # >0 means warn user
    }


def action_launch(args) -> Any:
    from . import launcher, db
    db.init_db()
    pid = _resolve_profile(args.profile)
    headless = _parse_headless(args.headless)
    try:
        child_pid = launcher.launch_detached(
            pid, headless=headless, start_url=args.url,
        )
    except RuntimeError as e:
        # already running
        raise SidecarError("already_running", str(e))
    return {
        "profile_id": pid,
        "pid": child_pid,
        "log_path": str(paths.profiles_dir / f"profile_{pid}" / "launcher.log"),
    }


def action_stop(args) -> Any:
    from . import launcher, db
    db.init_db()
    pid = _resolve_profile(args.profile)
    was_running_pid = db.is_running(pid)
    ok = launcher.stop(pid)
    return {
        "profile_id": pid,
        "stopped": ok,
        "previous_pid": was_running_pid,
    }


def action_delete(args) -> Any:
    from . import db
    db.init_db()
    pid = _resolve_profile(args.profile)
    if db.is_running(pid):
        raise SidecarError(
            "still_running",
            f"profile {pid} is running — stop it before delete",
        )
    db.delete_profile(pid)
    return {"profile_id": pid, "deleted": True}


def action_status(args) -> Any:
    from . import db, launcher
    db.init_db()
    pid = _resolve_profile(args.profile)
    row = db.get_profile(pid)
    if row is None:
        raise SidecarError("not_found", f"profile {pid} not found")
    running_pid = db.is_running(pid)
    log_path = paths.profiles_dir / f"profile_{pid}" / "launcher.log"
    return {
        "profile_id": pid,
        "status": row["status"],
        "running": running_pid is not None,
        "pid": running_pid,
        "log_path": str(log_path) if log_path.exists() else None,
    }


def action_log_tail(args) -> Any:
    """Return last N bytes of launcher.log (default 8KB). GUI polls it."""
    from . import db
    db.init_db()
    pid = _resolve_profile(args.profile)
    log_path = paths.profiles_dir / f"profile_{pid}" / "launcher.log"
    if not log_path.exists():
        raise SidecarError("no_log", f"no launcher.log yet at {log_path}")
    nbytes = max(64, min(args.bytes, 1_000_000))   # clamp 64B .. 1MB
    size = log_path.stat().st_size
    with open(log_path, "rb") as f:
        if size > nbytes:
            f.seek(-nbytes, 2)
            chunk = f.read()
        else:
            chunk = f.read()
    text = chunk.decode("utf-8", errors="replace")
    # Cut leading partial line (we read from middle of file)
    if size > nbytes and "\n" in text:
        text = text.split("\n", 1)[1]
    return {"profile_id": pid, "bytes": len(text), "log": text}


def action_presets(args) -> Any:
    from . import presets
    return {"presets": presets.PRESETS}


# --- Arg parsing -------------------------------------------------------------

def _parse_headless(s: str):
    if s == "true":
        return True
    if s == "false":
        return False
    return s   # 'virtual' or anything else passes through


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="phantom-sidecar",
        description="JSON-RPC layer for the Phantom Browser GUI. Prints one JSON object to stdout.",
        add_help=True,
    )
    sub = p.add_subparsers(dest="action", required=True)

    a = sub.add_parser("list", help="List all profiles")
    a.add_argument("--platform", default=None,
                   choices=["facebook", "tiktok", "chatgpt", "custom"])
    a.set_defaults(handler=action_list)

    a = sub.add_parser("get", help="Profile detail (no secrets)")
    a.add_argument("profile")
    a.set_defaults(handler=action_get)

    a = sub.add_parser("create", help="Create a profile")
    a.add_argument("--name", required=True)
    a.add_argument("--platform", required=True,
                   choices=["facebook", "tiktok", "chatgpt", "custom"])
    a.add_argument("--proxy", required=True,
                   help="host:port:user:pass")
    a.add_argument("--tz", default=None)
    a.add_argument("--notes", default=None)
    a.set_defaults(handler=action_create)

    a = sub.add_parser("launch", help="Launch detached browser for a profile")
    a.add_argument("profile")
    a.add_argument("--url", default=None)
    a.add_argument("--headless", default="virtual")
    a.set_defaults(handler=action_launch)

    a = sub.add_parser("stop", help="Stop a running browser")
    a.add_argument("profile")
    a.set_defaults(handler=action_stop)

    a = sub.add_parser("delete", help="Delete a profile (refuses if running)")
    a.add_argument("profile")
    a.set_defaults(handler=action_delete)

    a = sub.add_parser("status", help="Get running status + log path")
    a.add_argument("profile")
    a.set_defaults(handler=action_status)

    a = sub.add_parser("log-tail", help="Tail last N bytes of launcher.log")
    a.add_argument("profile")
    a.add_argument("--bytes", type=int, default=8192)
    a.set_defaults(handler=action_log_tail)

    a = sub.add_parser("presets", help="List platform presets")
    a.set_defaults(handler=action_presets)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse error → emit error envelope + exit 0 so Rust can parse
        _emit(False, error={"code": "bad_args",
                            "message": "argument parse failed"})
        return 0

    try:
        data = args.handler(args)
        _emit(True, data)
        return 0
    except SidecarError as e:
        _emit(False, error={
            "code": e.code,
            "message": e.message,
            "detail": e.detail,
        })
        return 0
    except Exception as e:   # last-ditch so Rust always gets JSON
        _emit(False, error={
            "code": "panic",
            "message": f"{type(e).__name__}: {e}",
            "detail": traceback.format_exc(limit=6),
        })
        return 0


if __name__ == "__main__":
    sys.exit(main())
