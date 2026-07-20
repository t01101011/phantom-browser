"""Launch / stop Camoufox instances per profile.

Two launch modes:

  * `launch_blocking` — open the browser, run an optional probe callback,
    close on Ctrl+C. Blocks until the browser exits. Used by CLI `launch`
    and `verify`, and by `launch_detached` in a subprocess.

  * `launch_detached` — spawn a long-lived subprocess that runs
    `launch_blocking` independently of the parent. Needed so the Tauri
    GUI can launch + stop without keeping the Camoufox context in the
    parent process. Returns immediately after recording the child pid.

Cookie/session persistence is handled via Camoufox's `persistent_context=True`
+ `user_data_dir`. This routes through Playwright's
`firefox.launch_persistent_context` so cookies, localStorage, IndexedDB
and (with the right prefs) service workers survive across launches.

Config building is shared via identity.build_launch_config(profile).
"""
from __future__ import annotations
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import db
from .identity import build_launch_config
from . import paths
from .runtime.registry import ProcessRegistry

# Module-level registry for in-memory worker tracking
# Used alongside the DB for fast lookups and crash recovery
_registry = ProcessRegistry()


def get_registry() -> ProcessRegistry:
    """Return the module-level ProcessRegistry instance."""
    return _registry


DATA_DIR = paths.profiles_dir   # per-profile user_data_dir roots

IS_WINDOWS = platform.system() == "Windows"


def _proxy_dict(profile: dict) -> dict:
    """Build Camoufox proxy dict (server'http://h:p', username, password)."""
    return {
        "server":   f"http://{profile['proxy_host']}:{profile['proxy_port']}",
        "username": profile["proxy_user"],
        "password": profile["proxy_pass"],
    }


def _ensure_user_data_dir(profile_id: int) -> Path:
    p = DATA_DIR / f"profile_{profile_id}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def launch_blocking(
    profile_id: int,
    probe: Optional[Callable[[Any], None]] = None,
    headless: str | bool = "virtual",
    start_url: Optional[str] = None,
    persistent: bool = True,
) -> dict:
    """Launch Camoufox for profile_id and block until the browser exits.

    `headless='virtual'` (Xvfb) is the default on Linux servers (gives
    Firefox a display so WebGL is enabled + canvas rasterizer is the
    real one). On Windows set headless=False (real GUI) or True (headless).

    `probe(page)` runs after start_url is loaded, if given. Use it for
    end-to-end verification: query navigator.userAgent, ip-api, etc.

    `persistent=True` (default) passes user_data_dir + persistent_context=True
    to Camoufox so cookies/localStorage/IndexedDB survive across launches.
    Set to False only for throwaway probes.

    Returns a dict of probe results (or {} if no probe).
    """
    from camoufox.sync_api import Camoufox

    profile = db.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"profile {profile_id} not found")

    running_pid = db.is_running(profile_id)
    if running_pid and running_pid != os.getpid() and _pid_alive(running_pid):
        raise RuntimeError(
            f"profile {profile_id} ({profile['name']}) already running as pid {running_pid}"
        )

    # Stale entry (crashed previous run, or my own slot recorded by the
    # parent before exec in detached mode) — clear it before re-recording.
    if running_pid and running_pid != os.getpid():
        db.mark_stopped(profile_id)

    udd = _ensure_user_data_dir(profile_id)
    fp_obj, config = build_launch_config(profile)

    # Persist the user_data_dir back to the DB so we can reuse it on relaunch
    db.update_profile(profile_id, {"user_data_dir": str(udd)})
    db.set_status(profile_id, "running")

    # Write own pid so /stop and other processes can kill us
    db.mark_running(profile_id, os.getpid())

    browser_kwargs: dict[str, Any] = dict(
        headless=headless,
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=_proxy_dict(profile),
        geoip=True,
        block_webrtc=True,
        config=config,
        debug=False,
    )
    if persistent:
        # Routes through playwright.firefox.launch_persistent_context.
        # The result is a BrowserContext (not a Browser), so cookies/
        # localStorage/IndexedDB persist in user_data_dir across launches.
        browser_kwargs["persistent_context"] = True
        browser_kwargs["user_data_dir"] = str(udd)

    results: dict = {}
    try:
        with Camoufox(**browser_kwargs) as browser:
            # persistent_context → browser is already a BrowserContext;
            # non-persistent → browser is a Browser, need new_context().
            context = browser if hasattr(browser, "new_page") else browser.new_context()
            page = context.new_page()
            if start_url:
                page.goto(start_url, timeout=30000, wait_until="domcontentloaded")
            if probe is not None:
                results = probe(page) or {}
            # Wait for user/Monitor to close the browser. In headless mode this
            # waits indefinitely until killed; in GUI mode the user closes.
            print(f"[phantom] profile {profile_id} ({profile['name']}) running. "
                  f"Ctrl+C to stop.", file=sys.stderr)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    finally:
        db.mark_stopped(profile_id)
        db.set_status(profile_id, "idle")

    return results


def launch_detached(
    profile_id: int,
    headless: str | bool = "virtual",
    start_url: Optional[str] = None,
    probe: bool = False,
) -> int:
    """Spawn a subprocess that runs launch_blocking; return its pid.

    The parent process (CLI sidecar, Tauri GUI) does NOT keep the Camoufox
    context in-process and can exit cleanly without killing the browser.
    The child writes its stdout/stderr to profiles_data/profile_<id>/launcher.log
    so Phase 2 GUI can tail it; the parent returns immediately after recording
    the child pid in the DB (which `stop()` reads to find the process to kill).
    """
    profile = db.get_profile(profile_id)
    if profile is None:
        raise ValueError(f"profile {profile_id} not found")

    running_pid = db.is_running(profile_id)
    if running_pid and _pid_alive(running_pid):
        # Real running browser exists — refuse the launch
        raise RuntimeError(
            f"profile {profile_id} ({profile['name']}) already running as pid {running_pid}"
        )
    if running_pid:
        # Stale row from a crashed/killed previous run — clear before re-launch.
        # launch_blocking (the eventual child) also has this guard, but clearing
        # here prevents the parent from raising the same RuntimeError to the GUI.
        db.mark_stopped(profile_id)

    udd = _ensure_user_data_dir(profile_id)
    log_path = udd / "launcher.log"

    # Normalise headless kwarg for the CLI
    if headless is True:
        headless_arg = "true"
    elif headless is False:
        headless_arg = "false"
    else:
        headless_arg = "virtual"

    argv: list[str] = [
        sys.executable, "-m", "phantom.cli",
        "detached",
        str(profile_id),
        "--headless", headless_arg,
    ]
    if start_url:
        argv += ["--url", start_url]
    if probe:
        argv += ["--probe"]

    # Start child in its own process group so SIGTERM to the child doesn't
    # shoot the parent. Detached subprocess is how Phase 2 GUI will run it.
    log_f = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        argv,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,   # new pgid; setpgid(0,0)
        cwd=str(paths.data_dir),
    )
    # setup environment loaded by CLI itself
    log_f.close()

    db.update_profile(profile_id, {"user_data_dir": str(udd)})
    db.mark_running(profile_id, proc.pid)
    db.set_status(profile_id, "running")

    # Register with in-memory ProcessRegistry
    try:
        _registry.register(
            profile_id=profile_id,
            pid=proc.pid,
            launched_by="detached",
            log_path=str(log_path),
        )
        _registry.mark_ready(profile_id)
    except (ValueError, Exception):
        pass  # Non-fatal — DB is the source of truth

    return proc.pid


def _descendants(parent_pid: int) -> list[int]:
    """Return pids of all descendants of parent_pid (recursive, any pgid).

    Camoufox spawns its own helpers (playwright node, Xvfb) in new sessions
    via setsid() so they get a fresh pgid — killpg(parent_pgid) misses them.
    This walks /proc/<pid>/stat (child → parent) to find every process whose
    ancestor chain passes through parent_pid, then signal them by pid.

    Windows: returns [] — `_kill_tree_windows` uses `taskkill /T` instead.
    """
    if IS_WINDOWS:
        # On Windows there is no /proc. Process-tree kill is done via
        # `taskkill /T /PID <pid>` (kills pid + all descendants) or via the
        # Win32 Toolhelp32 snapshot — see `_kill_tree_windows()`.
        return []

    # Build pid → ppid map from /proc
    ppid_of: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_bytes().split(b")", 1)[1].split()
            # fields after comm: state(0) ppid(1) pgid(2) ...
            ppid = int(stat[1])
            ppid_of[int(entry.name)] = ppid
        except (FileNotFoundError, ProcessLookupError, ValueError, IndexError):
            continue

    def is_descendant(pid: int) -> bool:
        cur = pid
        seen = set()
        while cur in ppid_of and cur not in seen:
            seen.add(cur)
            if ppid_of[cur] == parent_pid:
                return True
            cur = ppid_of[cur]
        return False

    return [pid for pid in ppid_of if is_descendant(pid)]


def _reap_zombies(pid: int, child_popen: "subprocess.Popen | None" = None) -> None:
    """Best-effort reap of a detached child so it doesn't linger as a zombie.

    launch_detached returns the child pid but drops the Popen handle, so when
    stop() kills the child nobody waitpid()s it on Linux → it sits as Z until
    init reaps it (often never, since init isn't our parent). We open /proc
    (i.e. adopt-or-poll) via waitpid(WNOHANG) on the pid; if we are not the
    parent this is a no-op. The real cleanup is `os.kill(pid, 0)` returning
    ENOENT after SIGKILL, which check_pid_dead below confirms.

    Windows: no-op — taskkill reaps its own targets.
    """
    if IS_WINDOWS:
        return
    try:
        if child_popen is not None:
            child_popen.wait(timeout=2)
    except Exception:
        pass


def _pid_dead(pid: int) -> bool:
    """True if pid does not exist (killed + reaped) — distinguishes a truly
    gone process from a zombie (which still answers os.kill(pid, 0)).

    Linux: /proc/<pid> existence. Windows: OpenProcess() via ctypes."""
    if IS_WINDOWS:
        return _pid_dead_windows(pid)
    return not Path(f"/proc/{pid}").exists()


# --- Windows helpers ---------------------------------------------------------

def _pid_dead_windows(pid: int) -> bool:
    """True if the Windows process no longer exists.

    Uses ctypes OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION). If the call
    fails (returns NULL / 0), the process is gone. We deliberately do NOT
    rely on `tasklist` parsing — that's slow and racy. This is the same
    check Task Manager does to grey out a dying process."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    SYNCHRONIZE = 0x00100000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not h:
        # OpenProcess returns NULL (0) when the process is gone OR we lack
        # access. ERROR_INVALID_PARAMETER (87) specifically means "no such
        # pid" — treat that as dead. Other errors -> conservatively alive.
        err = ctypes.get_last_error()
        return err == 87
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code)):
            return False
        return exit_code.value != STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def _kill_tree_windows(pid: int, force: bool = True) -> bool:
    """Kill `pid` and all descendants on Windows.

    Uses `taskkill /T /PID <pid> [/F]`:
      /T  terminate the process tree (all children recursively)
      /F  force (SIGKILL equivalent). Without /F, taskkill sends a WM_CLOSE
          to GUI apps and Ctrl+Break to console — flaky for Firefox+node.
          We use /F by default to match Linux SIGKILL aggressiveness.
    Returns True if taskkill ran without "process not found" error.
    """
    args = ["taskkill", "/T", "/PID", str(pid)]
    if force:
        args.insert(1, "/F")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        # taskkill exit codes: 0 = ok, 128 = not found, 1 = generic failure
        # "ERROR: The process ... not found." -> already dead, treat as success
        out = (r.stdout + r.stderr).lower()
        if r.returncode == 0:
            return True
        if "not found" in out or "no running instance" in out:
            return True
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _stop_windows(profile_id: int, pid: int) -> bool:
    """Windows port of stop(): taskkill /T /F the PID, poll for exit."""
    # taskkill /F /T already escalates to SIGKILL-equivalent immediately,
    # so no separate TERM phase. Poll for the process to actually die so
    # the DB row isn't cleared while Firefox is still flushing cookies.
    _kill_tree_windows(pid, force=True)
    for _ in range(20):   # up to 4 s
        time.sleep(0.2)
        if _pid_dead(pid):
            break
    db.mark_stopped(profile_id)
    db.set_status(profile_id, "idle")
    return True


def _pid_alive(pid: int) -> bool:
    if IS_WINDOWS:
        return not _pid_dead_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def stop(profile_id: int) -> bool:
    """Signal a running browser to stop (SIGTERM, then SIGKILL).

    Uses the ProcessRegistry first (in-memory kill), then falls back
    to manual /proc walk as before.

    Robust against Camoufox's setsid() grandchildren (Xvfb, playwright node):
    we signal the recorded pid's process group FIRST (fast path, kills the
    main children that share the pgid), then walk /proc for any setsid'd
    descendants that escaped the group and SIGKILL them explicitly. Only
    returns once the recorded pid is truly gone from /proc (not just a zombie)
    AND the DB row is cleared.

    Works for both:
      - blocking launches (parent pid in DB == caller's pid)
      - detached launches (child pid in DB == subprocess pid)
    """
    # The DB row is the durable source of truth.  A registry entry without a
    # matching running row is stale (for example after crash recovery or test
    # isolation) and must not turn a no-op stop into a reported success.
    pid = db.is_running(profile_id)
    if not pid:
        _registry.unregister(profile_id)
        return False

    # Try registry-based stop first (handles in-memory + DB tracking).
    reg_result = _registry.stop_worker(profile_id)
    if reg_result.get("error") != "not_found":
        # Registry attempted a kill (even if partial; DB already cleared).
        return reg_result.get("still_alive", []) == []

    # Registry has no record — fall back to the durable DB pid.

    if IS_WINDOWS:
        # Windows: no signals, no /proc, no killpg. Use taskkill /T /F to
        # kill the whole tree (Camoufox spawns Firefox + geckodriver + node
        # driver — all are descendants of the recorded pid on Windows). The
        # recorded pid from launch_detached is the python-sidecar subprocess
        # pid when shipped, or the camoufox-launcher pid when bundled.
        return _stop_windows(profile_id, pid)

    def _sig(s: int):
        """Signal the pgid first (group), then the bare pid (fallback), then
        any descendants that setsid'd out of the group."""
        try:
            os.killpg(pid, s)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            os.kill(pid, s)
        except (ProcessLookupError, PermissionError):
            pass
        # setsid'd grandchildren (Xvfb etc.) — kill by explicit pid
        for dpid in _descendants(pid):
            try:
                os.kill(dpid, s)
            except (ProcessLookupError, PermissionError):
                pass

    try:
        _sig(signal.SIGTERM)
        # Wait up to 3 s for graceful exit (Firefox flushing cookies/profile)
        for _ in range(10):
            time.sleep(0.3)
            if _pid_dead(pid) and not _descendants(pid):
                db.mark_stopped(profile_id)
                db.set_status(profile_id, "idle")
                return True
        # SIGKILL everything
        _sig(signal.SIGKILL)
        # Final wait
        for _ in range(10):
            time.sleep(0.2)
            if _pid_dead(pid) and not _descendants(pid):
                break
        db.mark_stopped(profile_id)
        db.set_status(profile_id, "idle")
        return True
    except ProcessLookupError:
        db.mark_stopped(profile_id)
        db.set_status(profile_id, "idle")
        return False


# --- Probes (used by CLI / tests) ---------------------------------------------

def probe_identity(page) -> dict:
    """End-to-end verification: exit IP + UA + timezone + WebGL + screen."""
    page.goto(
        "http://ip-api.com/json?fields=query,country,city,timezone",
        timeout=30000, wait_until="domcontentloaded",
    )
    ip_line = page.evaluate("() => document.body.innerText")
    return {
        "ip": ip_line,
        "self": page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                language: navigator.language,
                platform: navigator.platform,
                oscpu: navigator.oscpu,
                screenW: screen.width, screenH: screen.height,
                outerW: window.outerWidth, outerH: window.outerHeight,
                innerW: window.innerWidth, innerH: window.innerHeight,
                screenY: window.screenY, histLen: window.history.length,
                DPR: window.devicePixelRatio,
                webglVendor:   dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL)   : 'null',
                webglRenderer:  dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'null',
            };
        }"""),
    }
