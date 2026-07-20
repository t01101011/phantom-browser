"""Linux process helpers for the worker registry.

Lifted from ``launcher.py`` patterns and made reusable.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any


def is_process_alive(pid: int) -> bool:
    """Return whether *pid* is a live (non-zombie) Linux process.

    ``/proc/<pid>`` remains present for zombies, but a zombie cannot execute,
    receive a useful signal, or own browser descendants. Treating it as alive
    made termination falsely report survivors until an external owner happened
    to call ``wait(2)``.
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
        # ``comm`` is parenthesised and can contain spaces/parentheses. The
        # final ``)`` is followed by the one-byte process state.
        state = raw.rsplit(b")", 1)[1].split()[0]
        return state not in {b"Z", b"X", b"x"}
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError):
        return False


def _reap_if_child(pid: int) -> None:
    """Non-blockingly reap *pid* when it is owned by this process."""
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, ProcessLookupError):
        pass


def get_descendants(pid: int) -> list[int]:
    """Return PIDs of all descendants of *pid* by walking /proc.

    Handles race conditions where a child exits while we read /proc.
    """
    ppid_of: dict[int, int] = {}
    proc = Path("/proc")
    if not proc.exists():
        return []
    try:
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                stat = (entry / "stat").read_bytes().split(b")", 1)[1].split()
                ppid = int(stat[1])
                ppid_of[int(entry.name)] = ppid
            except (FileNotFoundError, ProcessLookupError, ValueError, IndexError):
                continue
    except PermissionError:
        return []

    def _is_descendant(cur: int, seen: set | None = None) -> bool:
        if seen is None:
            seen = set()
        while cur in ppid_of and cur not in seen:
            seen.add(cur)
            if ppid_of[cur] == pid:
                return True
            cur = ppid_of[cur]
        return False

    return [p for p in ppid_of if _is_descendant(p)]


def kill_process_tree(
    pid: int,
    sigterm_timeout: float = 5.0,
    sigkill_delay: float = 1.0,
) -> dict[str, Any]:
    """Kill *pid* and all its descendants.

    1. SIGTERM *pid* and all descendants.
    2. Wait *sigterm_timeout* seconds.
    3. SIGKILL survivors.
    4. Return summary dict.
    """
    result: dict[str, Any] = {"pid": pid, "signaled": [], "survivors": []}

    targets = [pid] + get_descendants(pid)
    targets = list(dict.fromkeys(targets))  # deduplicate, preserve order

    # SIGTERM phase
    for t in targets:
        try:
            os.kill(t, signal.SIGTERM)
            result["signaled"].append(t)
        except ProcessLookupError:
            pass
        except PermissionError:
            result["survivors"].append(t)

    time.sleep(min(sigterm_timeout, 2.0))

    # SIGKILL phase for survivors
    survivors = [t for t in targets if is_process_alive(t)]
    for t in survivors:
        try:
            os.kill(t, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            result["survivors"].append(t)

    time.sleep(sigkill_delay)

    # Registry PIDs are normally direct worker children. Reap those we own so
    # the kernel does not retain zombies. Non-child descendants are reaped by
    # their parent/init and are already considered dead above.
    for t in targets:
        _reap_if_child(t)

    result["still_alive"] = [t for t in targets if is_process_alive(t)]
    return result


def get_process_info(pid: int) -> dict[str, Any]:
    """Return basic resource info for a process (CPU, memory).

    Returns empty dict if process is gone or unreadable.
    """
    info: dict[str, Any] = {"pid": pid}
    try:
        proc_dir = Path(f"/proc/{pid}")
        if not proc_dir.exists():
            return {}

        # Parse /proc/pid/stat for CPU time
        stat_raw = (proc_dir / "stat").read_bytes()
        stat_parts = stat_raw.split(b")", 1)[1].split() if b")" in stat_raw else []
        if len(stat_parts) >= 13:
            info["utime"] = int(stat_parts[11])
            info["stime"] = int(stat_parts[12])

        # Parse /proc/pid/status for memory
        status_text = (proc_dir / "status").read_text()
        for line in status_text.splitlines():
            if line.startswith("VmRSS:"):
                info["rss_kb"] = int(line.split()[1])
            elif line.startswith("Threads:"):
                info["threads"] = int(line.split()[1])

        # Parse /proc/pid/cmdline
        cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").strip()
        info["cmdline"] = cmdline.decode("utf-8", errors="replace")

        info["alive"] = True
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return {}

    return info
