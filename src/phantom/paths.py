"""Cross‑platform paths for Phantom Browser.

Uses ``platformdirs`` (via ``user_data_dir``) on every system so that data
lives in the correct OS‑specific location:

  - **Linux:**   ``~/.local/share/phantom/``
  - **macOS:**   ``~/Library/Application Support/phantom/``
  - **Windows:** ``%LOCALAPPDATA%\\phantom\\phantom\\``

Override the base directory by setting the ``PHANTOM_DATA_DIR`` environment
variable to an absolute path.

All path attributes are **lazily resolved** — they read the environment
variable on first access and cache the result.  Call ``reload_paths()``
after changing ``PHANTOM_DATA_DIR`` to flush the cache (useful in tests).
"""
from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

__all__ = [
    "data_dir",
    "profiles_dir",
    "artifacts_dir",
    "db_path",
    "runtime_dir",
    "reload_paths",
]

# ── Internal helpers ─────────────────────────────────────────────────────────


def _resolve_data_dir() -> Path:
    """Resolve the base data directory from env or platform default."""
    override = os.environ.get("PHANTOM_DATA_DIR")
    return (
        Path(override).resolve()
        if override
        else Path(user_data_dir("phantom", "phantom"))
    )


def reload_paths() -> None:
    """No-op — paths are resolved lazily every time (no cache)."""
    pass


# ── Module-level __getattr__ (Python 3.7+) ──────────────────────────────────
# `import phantom.paths as p; p.data_dir` returns a Path, just like before —
# but now it reads the env var on every access, so tests that change
# PHANTOM_DATA_DIR and call reload_paths() get the correct value.
# The performance cost of re-reading the env var is negligible for a
# control-plane API that resolves paths at most a few hundred times/day.


def __getattr__(name: str) -> Path:
    """Lazily resolve and return a path attribute (no caching)."""
    dd = _resolve_data_dir()
    if name == "data_dir":
        return dd
    if name == "profiles_dir":
        return dd / "profiles"
    if name == "artifacts_dir":
        return dd / "artifacts"
    if name == "db_path":
        return dd / "phantom.db"
    if name == "runtime_dir":
        return dd / "runtime"
    raise AttributeError(f"module 'phantom.paths' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(__all__))
