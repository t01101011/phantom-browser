"""Worker process main entry point.

A worker subprocess runs a single browser engine (Camoufox by default)
and communicates via structured JSON events on stdout.

Usage
-----
.. code-block:: bash

    python -m phantom.workers.main --profile-id 1

The worker reads the profile from the DB, prepares the engine, launches
the browser, and emits events until stopped.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import threading
import queue
import base64
from typing import Any

from phantom.workers.protocol import Event


# Flag for graceful shutdown
_running = True


def _handle_signal(signum: int, frame: Any = None) -> None:
    global _running
    _running = False


def emit(event: Event) -> None:
    """Write a JSON event to stdout and flush immediately."""
    print(event.to_json(), flush=True)


def main(argv: list[str] | None = None) -> None:
    """Worker main entry point.

    Parses CLI args, loads the profile, runs the engine lifecycle,
    and emits events to stdout.
    """
    parser = argparse.ArgumentParser(description="Phantom Browser worker")
    parser.add_argument("--profile-id", type=int, required=True, help="Profile ID to run")
    parser.add_argument("--data-dir", default=None, help="PHANTOM_DATA_DIR override")
    parser.add_argument("--headless", default=None, help="headless mode override")
    parser.add_argument("--url", default=None, help="Start URL")
    args = parser.parse_args(argv)

    if args.data_dir:
        os.environ["PHANTOM_DATA_DIR"] = args.data_dir

    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Load profile from DB
    from phantom import db
    db.init_db()

    profile = db.get_profile(args.profile_id)
    if profile is None:
        emit(Event("error", data={}, error={
            "code": "PROFILE_NOT_FOUND",
            "message": f"Profile {args.profile_id} not found",
        }))
        sys.exit(1)

    # The same frozen executable is re-entered as a worker. Runtime-hook state
    # is not a reliable contract across that child boundary, so derive and set
    # the packaged browser root explicitly before constructing the engine.
    if getattr(sys, "frozen", False):
        executable_root = os.path.dirname(os.path.abspath(sys.executable))
        bundled_roots = (
            os.path.join(executable_root, "_internal", "camoufox"),
            os.path.join(executable_root, "camoufox"),
        )
        bundled_root = next(
            (
                root for root in bundled_roots
                if any(os.path.isfile(os.path.join(root, name)) for name in ("camoufox.exe", "camoufox-bin.exe"))
            ),
            None,
        )
        if bundled_root:
            os.environ["PHANTOM_CAMOUFOX_DIR"] = bundled_root

    # Build engine
    from phantom.engines.camoufox import CamoufoxEngine
    engine = CamoufoxEngine(profile)

    emit(Event("start", data={"profile_id": args.profile_id, "pid": os.getpid()}))

    try:
        # Prepare + start
        launch_config = {"headless": args.headless} if args.headless is not None else None
        engine.prepare(launch_config)
        emit(Event("prepared", data={"status": "prepared"}))

        engine.start()
        emit(Event("started", data={"pid": os.getpid()}))

        engine.ready()
        emit(Event("ready", data={"status": "ok"}))

        # Navigate to start URL if provided
        if args.url:
            result = engine.navigate(args.url)
            emit(Event("navigate", data=result))

        # Read JSON-line action commands on a side thread; browser calls remain
        # on this main thread because Playwright's sync API is thread-affine.
        commands: queue.Queue[dict[str, Any]] = queue.Queue()
        def read_commands() -> None:
            for line in sys.stdin:
                try:
                    commands.put(json.loads(line))
                except json.JSONDecodeError:
                    emit(Event("protocol_error", error={"code":"INVALID_JSON","message":"invalid command"}))
        threading.Thread(target=read_commands, daemon=True).start()
        from phantom.agent.actions import ActionController, ActionError
        controller = ActionController(engine._page, event_sink=lambda typ,data: emit(Event(typ, data=data)), seed=args.profile_id)

        # Main loop: process actions, emit heartbeat and wait for shutdown
        heartbeat_interval = 5  # seconds
        last_heartbeat = time.monotonic()

        while _running:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                command = None
            if command and command.get("type") == "action":
                rid = command.get("request_id")
                try:
                    name = command["action"]
                    if name not in {"navigate","snapshot","click","type","press","scroll","select","screenshot"}:
                        raise ActionError("UNKNOWN_ACTION", f"unknown action {name!r}")
                    data = getattr(controller, name)(**command.get("args", {}))
                    if isinstance(data, bytes):
                        data = {"mime":"image/png", "bytes":base64.b64encode(data).decode("ascii")}
                    print(json.dumps({"type":"action_result","request_id":rid,"data":data}), flush=True)
                except Exception as exc:
                    print(json.dumps({"type":"action_result","request_id":rid,"error":{"code":getattr(exc,"code","ACTION_FAILED"),"message":str(exc)}}), flush=True)
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                emit(Event("heartbeat", data={"status": engine._status}))
                last_heartbeat = now
            time.sleep(0.5)

    except Exception as exc:
        emit(Event("error", data={}, error={
            "code": "ENGINE_ERROR",
            "message": str(exc),
            "exception_type": type(exc).__name__,
        }))
        exit_code = 1
    else:
        exit_code = 0
    finally:
        result = engine.stop()
        emit(Event("stopped", data=result))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
