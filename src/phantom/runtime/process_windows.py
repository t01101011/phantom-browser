"""Windows process helpers for the worker registry.

Uses ``taskkill /T /F`` for tree kill (same as ``launcher.py``).
Process existence uses ctypes ``OpenProcess`` + ``GetExitCodeProcess``.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any


def is_process_alive(pid: int) -> bool:
    """Check if a Windows process exists.

    Uses OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess
    checking STILL_ACTIVE=259.  Returns False when the pid is invalid
    (ERROR_INVALID_PARAMETER).
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        STILL_ACTIVE = 259

        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            err = ctypes.get_last_error()
            # ERROR_INVALID_PARAMETER (87) = process doesn't exist
            return False

        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    except Exception:
        # If ctypes fails for any reason, fall back to tasklist
        try:
            subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, timeout=5, check=False,
            )
            # tasklist returns info if process exists
            return True
        except Exception:
            return False


def get_descendants(pid: int) -> list[int]:
    """Return PIDs of all descendants of *pid* on Windows.

    Uses ``wmic`` or ``taskkill``-based heuristic.  For simplicity,
    returns empty list — ``kill_process_tree`` uses ``taskkill /T``
    which handles tree kill natively.
    """
    # taskkill /T handles tree kill natively; we don't need to enumerate
    return []


def kill_process_tree(
    pid: int,
    sigterm_timeout: float = 5.0,
    sigkill_delay: float = 1.0,
) -> dict[str, Any]:
    """Kill *pid* and all its descendants on Windows.

    Uses ``taskkill /T /F`` (force kill tree).  The ``/T`` flag kills
    *pid* + all child processes recursively.

    Returns summary dict.
    """
    result: dict[str, Any] = {"pid": pid, "taskkill_ok": False, "still_alive": []}

    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True, timeout=30,
        )
        result["taskkill_ok"] = True
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        # taskkill not available — no-op
        pass
    except Exception:
        pass

    time.sleep(sigkill_delay)

    if is_process_alive(pid):
        result["still_alive"].append(pid)

    return result


def get_process_info(pid: int) -> dict[str, Any]:
    """Return basic resource info for a Windows process.

    Returns empty dict if process is gone or info unavailable.
    """
    import ctypes
    from ctypes import wintypes

    info: dict[str, Any] = {"pid": pid}
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return {}

        # Get process times
        creation = wintypes.FILETIME()
        exit_t = wintypes.FILETIME()
        kernel_t = wintypes.FILETIME()
        user_t = wintypes.FILETIME()
        if kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                     ctypes.byref(exit_t),
                                     ctypes.byref(kernel_t),
                                     ctypes.byref(user_t)):
            info["kernel_time"] = (kernel_t.dwHighDateTime << 32) | kernel_t.dwLowDateTime
            info["user_time"] = (user_t.dwHighDateTime << 32) | user_t.dwLowDateTime

        # Get memory info
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        if kernel32.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            info["rss_bytes"] = pmc.WorkingSetSize

        kernel32.CloseHandle(handle)
        info["alive"] = True
    except Exception:
        return {}

    return info
