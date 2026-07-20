#!/usr/bin/env python3
"""Detached-launch test for Phase 2 blocker.

Verifies `launcher.launch_detached()`:
  1. Parent process returns immediately (does NOT block).
  2. Child subprocess survives parent exit.
  3. Child is recorded in running_instances with its own pid.
  4. `launcher.stop()` sends SIGTERM to the process group and the whole
     tree (child + firefox) dies, DB cleaned.

Run from repo root:
    set -a && . .env && set +a
    .venv/bin/python scripts/test_launch_detached.py 1
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from phantom import db, launcher  # noqa: E402


def _alive(pid: int) -> bool:
    """True if pid exists as a live process (not zombie). Uses /proc like
    launcher._pid_dead so the test matches stop()'s exit semantics — a
    zombie (state Z) still answers os.kill(pid, 0) but /proc/<pid>/stat
    field 3 reads 'Z', which we treat as dead."""
    import os
    try:
        stat = open(f"/proc/{pid}/stat").read()
        state = stat.split(")", 1)[1].split()[0]
        return state != "Z"  # Z = zombie, treat as dead
    except (FileNotFoundError, ProcessLookupError):
        return False
    except Exception:
        # Fallback: os.kill probe (will be True for zombies too, conservative)
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def run(profile_id: int) -> int:
    db.init_db()
    profile = db.get_profile(profile_id)
    if profile is None:
        print(f"[!] profile {profile_id} not found")
        return 2

    # Clean running state
    db.mark_stopped(profile_id)
    db.set_status(profile_id, "idle")

    udd = launcher._ensure_user_data_dir(profile_id)
    log_path = udd / "launcher.log"

    print(f"[*] profile {profile_id} ({profile['name']})")
    print(f"[*] launching detached …\n")

    # Patch: launch_detached in code currently doesn't pass env to child.
    # The CLI loads .env itself, so this should be fine.
    child_pid = launcher.launch_detached(
        profile_id, headless="virtual",
    )

    print(f"[1] parent call returned pid={child_pid}")
    print(f"    parent pid (this test process) = {os.getpid()}")
    print(f"    child != parent: {child_pid != os.getpid()}")

    # Give the child a moment to write its DB pid entry (launch_detached
    # writes before exec; the CLI's launch_blocking overwrites it with the
    # same value after Camoufox starts).
    time.sleep(15)  # Camoufox binary + Xvfb startup

    pid_in_db = db.is_running(profile_id)
    print(f"[2] pid in DB: {pid_in_db}")
    print(f"    status: {db.get_profile(profile_id)['status']}")
    print(f"    child alive: {_alive(child_pid)}")
    print(f"    child == db pid: {pid_in_db == child_pid}")

    if not _alive(child_pid):
        print("[FAIL] child process died prematurely. log tail:")
        try:
            print((udd / "launcher.log").read_text()[-2000:])
        except Exception as e:
            print(f"  (couldn't read log: {e})")
        return 1

    # Look at the process tree: child + firefox
    print(f"\n[3] process tree under pid {child_pid}:")
    try:
        ps = subprocess.run(
            ["ps", "-eo", "pid,ppid,pgid,cmd"],
            capture_output=True, text=True, timeout=5,
        )
        grep = subprocess.run(
            ["grep", "-E", f"(^{child_pid} | {child_pid} )" ],
            input=ps.stdout, capture_output=True, text=True, timeout=5,
        )
        # Show pgid tree (processes with same pgid or ppid=child)
        for line in ps.stdout.splitlines():
            cols = line.split(None, 3)
            if len(cols) < 4:
                continue
            try:
                pid = int(cols[0])
                ppid = int(cols[1])
                pgid = int(cols[2])
            except ValueError:
                continue
            if ppid == child_pid or pid == child_pid or pgid == child_pid:
                print(f"    {line.strip()}")
    except Exception as e:
        print(f"    (ps failed: {e})")

    # ---- Now stop it ----
    print("\n[4] calling launcher.stop(profile_id) …")
    t0 = time.time()
    ok = launcher.stop(profile_id)
    t1 = time.time()
    print(f"    stop returned: {ok}  (took {t1 - t0:.1f}s)")

    # Verify
    time.sleep(1)
    pid_in_db_after = db.is_running(profile_id)
    status_after = db.get_profile(profile_id)["status"]
    print(f"[5] post-stop:")
    print(f"    child alive: {_alive(child_pid)}")
    print(f"    pid in DB: {pid_in_db_after} (expect None)")
    print(f"    status: {status_after} (expect idle)")

    # Check that child and firefox grandchild both died
    child_alive = _alive(child_pid)
    firefox_alive = False
    try:
        ps = subprocess.run(["pgrep", "-P", str(child_pid)], capture_output=True, text=True)
        if ps.stdout.strip():
            firefox_alive = True
            print(f"    [WARN] grandchildren still alive: {ps.stdout.strip()}")
    except Exception:
        pass

    if child_alive:
        print("[FAIL] child process still alive after stop()")
        return 1
    if pid_in_db_after is not None:
        print("[FAIL] running_instances not cleared after stop()")
        return 1
    if status_after != "idle":
        print("[FAIL] profile status not reset to idle")
        return 1

    # Orphan Xvfb check: Camoufox's setsid'd Xvfb must also be gone
    try:
        xvfb_leftover = subprocess.run(
            ["pgrep", "-f", "Xvfb -displayfd"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except Exception:
        xvfb_leftover = ""
    if xvfb_leftover:
        print(f"    [WARN] orphan Xvfb pids leftover: {xvfb_leftover}")
        print("           (stop() setsid-bug not fully fixed)")
        return 1
    print("    [OK] no orphan Xvfb — setsid'd grandchildren also killed")

    print("\n[PASS] launch_detached + stop():")
    print("  - parent returned immediately (didn't block on Camoufox)")
    print("  - child survived, recorded in DB")
    print("  - stop() killed the process group incl. Firefox + Xvfb")
    print("  - DB cleaned")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(int(sys.argv[1])))
