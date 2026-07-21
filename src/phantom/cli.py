"""phantom-cli — Phase 1 CLI for the backend.

Usage:
    python -m phantom.cli init
    python -m phantom.cli create <name> --platform <p> --proxy <h:p:u:pw> [--tz TZ]
    python -m phantom.cli list [--platform p]
    python -m phantom.cli show <name_or_id>
    python -m phantom.cli launch <name_or_id> [--probe] [--url URL] [--headless HEADLESS]
                                                [--detached]
    python -m phantom.cli stop <name_or_id>
    python -m phantom.cli delete <name_or_id>
    python -m phantom.cli verify <name_or_id>   # launch + probe + dump + exit
    python -m phantom.cli detached <id> [--headless H] [--url U] [--probe]
                                              # internal: invoked by launch_detached
    python -m phantom.cli serve [--host HOST] [--port PORT] [--log-level LEVEL]
                                [--allow-remote]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

# Load .env (PROXY_*, etc.) for local convenience
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip())


def resolve_profile_id(arg: str) -> int:
    """Resolve 'name' or '42' to profile id."""
    from . import db
    if arg.isdigit():
        return int(arg)
    row = db.get_profile_by_name(arg)
    if row is None:
        sys.exit(f"profile {arg!r} not found")
    return row["id"]


def _parse_headless(s: str):
    """'virtual' | 'true' | 'false' → keep as-is or cast to bool."""
    if s == "true":
        return True
    if s == "false":
        return False
    return s   # 'virtual' or anything else passes through


def cmd_init(args):
    from . import db
    db.init_db()
    print(f"[+] DB initialised at {db.DB_PATH()}")


def cmd_create(args):
    from . import db, identity, presets
    db.init_db()
    preset = presets.get_preset(args.platform)

    host, port, user, pw = args.proxy.split(":", 3)
    proxy_host, proxy_port = host, int(port)

    # Warn on duplicate proxy
    dup = db.proxy_usage_count(proxy_host, proxy_port)
    if dup > 0:
        print(f"[!] WARN: {dup} existing profile(s) already use "
              f"this proxy {proxy_host}:{proxy_port}. For FB/TikTok, one "
              f"profile per residential proxy (1:1) is strongly recommended.",
              file=sys.stderr)

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
        "user_data_dir":      "",
        "notes":              preset.get("notes_default", ""),
        **blobs,
    }
    pid = db.create_profile(row)
    print(f"[+] Created profile id={pid} name={args.name!r} platform={args.platform}")
    print(f"    proxy={proxy_host}:{proxy_port} tz={tz or '(geoip)'}")
    print(f"    fingerprint locked: webgl={json.loads(blobs['webgl_json']).get('webGl:vendor')!r}")


def cmd_list(args):
    from . import db
    db.init_db()
    rows = db.list_profiles(args.platform)
    if not rows:
        print("(no profiles)")
        return
    print(f"{'ID':>3}  {'NAME':<20} {'PLATFORM':<10} {'STATUS':<8} {'PROXY':<25} {'TZ':<18}")
    print("-" * 90)
    for r in rows:
        proxy = f"{r['proxy_host']}:{r['proxy_port']}"
        tz = r['timezone'] or '(geoip)'
        print(f"{r['id']:>3}  {r['name']:<20} {r['platform_tag']:<10} "
              f"{r['status']:<8} {proxy:<25} {tz:<18}")


def cmd_show(args):
    from . import db
    db.init_db()
    pid = resolve_profile_id(args.profile)
    row = db.get_profile(pid)
    if row is None:
        sys.exit(f"profile {args.profile} not found")
    kept = {k: v for k, v in row.items()
            if k not in ("proxy_pass", "fingerprint_json")}
    if "seeds_json" in kept:
        kept["seeds_json"] = json.loads(kept["seeds_json"])
    print(json.dumps(kept, indent=2, default=str))
    fp = json.loads(row["fingerprint_json"])
    print("\n-- fingerprint (extract) --")
    print(json.dumps({
        "userAgent": fp["navigator"].get("userAgent"),
        "screen":   fp["screen"],
        "language": fp["navigator"].get("language"),
    }, indent=2))


def cmd_launch(args):
    from . import launcher
    pid = resolve_profile_id(args.profile)
    probe = launcher.probe_identity if args.probe else None
    headless = _parse_headless(args.headless)

    if args.detached:
        child_pid = launcher.launch_detached(
            pid, headless=headless, start_url=args.url, probe=args.probe,
        )
        print(f"[+] launched detached pid={child_pid} for profile {pid}")
        print(f"    log: profiles_data/profile_{pid}/launcher.log")
        return

    res = launcher.launch_blocking(
        pid, probe=probe, headless=headless, start_url=args.url,
    )
    if res:
        print(json.dumps(res, indent=2, default=str))


def cmd_detached(args):
    """Internal subcommand: runs launch_blocking in a subprocess."""
    from . import launcher
    pid = int(args.profile)
    probe = launcher.probe_identity if args.probe else None
    headless = _parse_headless(args.headless)
    res = launcher.launch_blocking(
        pid, probe=probe, headless=headless, start_url=args.url,
        persistent=True,
    )
    if res:
        print(json.dumps(res, indent=2, default=str))


def cmd_verify(args):
    """Launch, run probe, dump exit IP + UA + WebGL, then exit."""
    from . import launcher
    pid = resolve_profile_id(args.profile)

    out = {}
    def quick_probe(page):
        out.update(launcher.probe_identity(page))
        raise KeyboardInterrupt
    headless = _parse_headless(args.headless) if args.headless != "auto" else "virtual"
    try:
        launcher.launch_blocking(pid, probe=quick_probe, headless=headless, persistent=False)
    except KeyboardInterrupt:
        pass
    print(json.dumps(out, indent=2, default=str))


def cmd_stop(args):
    from . import launcher
    pid = resolve_profile_id(args.profile)
    ok = launcher.stop(pid)
    print(f"[{'+' if ok else '-'}] stop {args.profile}: {'stopped' if ok else 'not running'}")


def cmd_serve(args):
    """Start the FastAPI control plane server.

    Binds to 127.0.0.1:5100 by default.  Explicit ``--host 0.0.0.0`` is
    rejected unless ``--allow-remote`` is also passed (security gate).
    """
    import uvicorn

    host = args.host or "127.0.0.1"
    if host == "0.0.0.0" and not args.allow_remote:
        sys.exit(
            "ERROR: Binding to 0.0.0.0 exposes the API to the network.\n"
            "  Pass --allow-remote to confirm this is intentional."
        )

    from phantom.api.app import create_app
    app = create_app()
    print(f"[+] Starting Phantom control plane at http://{host}:{args.port}")
    # PyInstaller builds the sidecar with ``console=False``.  In that mode
    # sys.stdout/sys.stderr can be None, while Uvicorn's default formatter
    # unconditionally calls sys.stdout.isatty().  Use Uvicorn's internal
    # defaults without dictConfig so the packaged sidecar can start headless.
    uvicorn.run(
        app,
        host=host,
        port=args.port,
        log_level=args.log_level or "info",
        log_config=None,
        access_log=False,
    )


def cmd_worker(args):
    """Internal frozen-sidecar entry point for one browser worker."""
    from phantom.workers.main import main as worker_main

    argv = ["--profile-id", str(args.profile_id)]
    if args.data_dir:
        argv += ["--data-dir", args.data_dir]
    if args.headless is not None:
        argv += ["--headless", args.headless]
    if args.url:
        argv += ["--url", args.url]
    worker_main(argv)


def cmd_delete(args):
    from . import db
    pid = resolve_profile_id(args.profile)
    if db.is_running(pid):
        sys.exit("profile is running — stop it first")
    db.delete_profile(pid)
    print(f"[+] Deleted profile {pid}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phantom-cli", description="Phantom Browser backend CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Initialise SQLite DB").set_defaults(func=cmd_init)

    c = sub.add_parser("create", help="Create a profile")
    c.add_argument("name")
    c.add_argument("--platform", required=True, choices=["facebook", "tiktok", "chatgpt", "custom"])
    c.add_argument("--proxy", required=True, help="host:port:user:pass (colons; pass may contain colons)")
    c.add_argument("--tz", default=None, help="Timezone override (default: geoip from proxy)")
    c.set_defaults(func=cmd_create)

    c = sub.add_parser("list", help="List profiles")
    c.add_argument("--platform", default=None, choices=["facebook", "tiktok", "chatgpt", "custom"])
    c.set_defaults(func=cmd_list)

    c = sub.add_parser("show", help="Show profile detail")
    c.add_argument("profile")
    c.set_defaults(func=cmd_show)

    c = sub.add_parser("launch", help="Launch browser for profile (blocking, or --detached)")
    c.add_argument("profile")
    c.add_argument("--url", default=None, help="Start URL")
    c.add_argument("--probe", action="store_true", help="Run identity probe at launch")
    c.add_argument("--headless", default="virtual",
                   help="'virtual' (Xvfb, default on linux), 'true', 'false'")
    c.add_argument("--detached", action="store_true",
                   help="Spawn a detached subprocess (GUI-friendly). "
                        "Parent returns immediately; log → profiles_data/profile_<id>/launcher.log")
    c.set_defaults(func=cmd_launch)

    c = sub.add_parser("detached", help="INTERNAL: child entry-point for launch_detached()")
    c.add_argument("profile", help="profile id (integer)")
    c.add_argument("--url", default=None, help="Start URL")
    c.add_argument("--probe", action="store_true", help="Run identity probe")
    c.add_argument("--headless", default="virtual",
                   help="'virtual' | 'true' | 'false'")
    c.set_defaults(func=cmd_detached)

    c = sub.add_parser("verify", help="Launch, probe identity, then exit (non-interactive)")
    c.add_argument("profile")
    c.add_argument("--headless", default="auto", help="'virtual' (default), 'true', 'false'")
    c.set_defaults(func=cmd_verify)

    c = sub.add_parser("stop", help="Stop running browser for profile")
    c.add_argument("profile")
    c.set_defaults(func=cmd_stop)

    c = sub.add_parser("delete", help="Delete a profile")
    c.add_argument("profile")
    c.set_defaults(func=cmd_delete)

    c = sub.add_parser("serve", help="Start FastAPI control plane server")
    c.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    c.add_argument("--port", type=int, default=5100, help="Port (default: 5100)")
    c.add_argument("--log-level", default="info", help="uvicorn log level")
    c.add_argument("--allow-remote", action="store_true",
                   help="Allow binding to 0.0.0.0 (dangerous without firewall)")
    c.set_defaults(func=cmd_serve)

    c = sub.add_parser("worker", help=argparse.SUPPRESS)
    c.add_argument("--profile-id", type=int, required=True)
    c.add_argument("--data-dir", default=None)
    c.add_argument("--headless", default=None)
    c.add_argument("--url", default=None)
    c.set_defaults(func=cmd_worker)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
