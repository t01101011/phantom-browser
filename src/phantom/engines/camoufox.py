"""Camoufox engine adapter.

Wraps Camoufox (patched Firefox) behind the ``BaseEngine`` contract.
Keeps the 6-blob persistent identity model and adds structured control.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

from phantom.engines.base import BaseEngine
from phantom import db as phantom_db


class CamoufoxEngine(BaseEngine):
    """Engine adapter for Camoufox (Firefox-based antidetect browser).

    Parameters
    ----------
    profile : dict
        Full profile row from the DB (or equivalent dict).  Must include
        the 6 identity blobs (fingerprint_json, seeds_json, webgl_json,
        fonts_json, voices_json, misc_json) plus proxy, locale, and
        timezone fields.
    data_dir : Path | str | None
        Base data directory for user_data_dir resolution.  Defaults to
        ``paths.profiles_dir``.
    """

    def __init__(
        self,
        profile: dict[str, Any],
        data_dir: Path | str | None = None,
    ) -> None:
        self._profile = dict(profile)  # copy so we don't mutate caller's dict
        self._data_dir = Path(data_dir) if data_dir else Path(os.environ.get(
            "PHANTOM_DATA_DIR",
            str(Path.home() / ".local" / "share" / "phantom"),
        )) / "profiles"

        self._fp_obj: Any = None
        self._config: dict[str, Any] = {}
        self._kwargs: dict[str, Any] = {}
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._status: str = "created"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _proxy_dict(self) -> dict[str, str]:
        """Build Camoufox proxy dict from profile data."""
        p = self._profile
        return {
            "server":   f"http://{p['proxy_host']}:{p['proxy_port']}",
            "username": p.get("proxy_user", ""),
            "password": p.get("proxy_pass", ""),
        }

    def _build_launch_config(self) -> tuple[Any, dict]:
        """Reconstruct Fingerprint obj + full deterministic config.

        Returns (Fingerprint, config_dict) — identical to
        ``identity.build_launch_config()``.
        """
        # Delay imports so camoufox/browserforge are optional at the
        # adapter-import level (only needed when actually launching).
        from phantom.identity import build_launch_config
        return build_launch_config(self._profile)

    def _ensure_user_data_dir(self) -> Path:
        profile_id = self._profile.get("id", 0)
        name = self._profile.get("name", f"profile_{profile_id}")
        p = self._data_dir / f"profile_{name}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── Engine contract ───────────────────────────────────────────────────────

    def prepare(self, config: dict | None = None) -> dict[str, Any]:
        """Validate profile and build launch kwargs.

        Returns ``{"status": "prepared", "kwargs": {...}}``.
        """
        if not self._profile.get("fingerprint_json"):
            raise ValueError("profile missing fingerprint_json — cannot prepare engine")

        self._fp_obj, self._config = self._build_launch_config()
        udd = self._ensure_user_data_dir()

        default_headless: str | bool = False if platform.system() == "Windows" else "virtual"
        self._kwargs = dict(
            headless=config.get("headless", default_headless) if config else default_headless,
            fingerprint=self._fp_obj,
            i_know_what_im_doing=True,
            block_webrtc=True,
            config=self._config,
            debug=False,
            persistent_context=True,
            user_data_dir=str(udd),
        )
        # Frozen releases stage the browser directly under
        # ``_internal/camoufox`` rather than Camoufox's user-cache/version
        # layout.  Bypass pkgman's cache resolver with the explicit executable.
        browser_roots: list[Path] = []
        configured_root = os.environ.get("PHANTOM_CAMOUFOX_DIR")
        if configured_root:
            browser_roots.append(Path(configured_root))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            browser_roots.append(Path(meipass) / "camoufox")
        if getattr(sys, "frozen", False):
            executable_root = Path(sys.executable).resolve().parent
            browser_roots.extend((
                executable_root / "_internal" / "camoufox",
                executable_root / "camoufox",
            ))

        executable: Path | None = None
        for browser_root in dict.fromkeys(browser_roots):
            # Do not gate this on platform detection. Frozen applications can
            # inherit stale build-time modules/constants; inspect every filename
            # the release contract permits and use what is physically present.
            candidates = [
                browser_root / "camoufox.exe",
                browser_root / "camoufox-bin.exe",
                browser_root / "camoufox-bin",
                browser_root / "Camoufox.app" / "Contents" / "MacOS" / "camoufox",
            ]
            executable = next((path for path in candidates if path.is_file()), None)
            if executable is not None:
                break
        if executable is not None:
            self._kwargs["executable_path"] = str(executable)
            version_file = executable.parent / "version.json"
            if not version_file.is_file():
                raise FileNotFoundError(f"bundled Camoufox version metadata missing: {version_file}")
            try:
                version_data = json.loads(version_file.read_text(encoding="utf-8"))
                firefox_version = str(version_data["version"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid bundled Camoufox version metadata: {version_file}") from exc
            # Camoufox otherwise calls installed_verstr(), which only understands
            # its user-cache/multiversion layout and rejects an explicit packaged
            # executable as "not installed".
            self._kwargs["ff_version"] = firefox_version
        elif getattr(sys, "frozen", False):
            checked = ", ".join(str(path) for path in dict.fromkeys(browser_roots))
            raise FileNotFoundError(f"bundled Camoufox executable missing; checked: {checked}")

        # Camoufox rejects an empty proxy URL. GeoIP matching is meaningful only
        # when an actual proxy is configured.
        if self._profile.get("proxy_host") and self._profile.get("proxy_port"):
            self._kwargs["proxy"] = self._proxy_dict()
            self._kwargs["geoip"] = True

        self._status = "prepared"
        return {"status": "prepared", "kwargs": self._kwargs}

    def start(self) -> dict[str, Any]:
        """Launch the Camoufox browser instance.

        Returns ``{"status": "started", "pid": <os_pid>}``.
        """
        from camoufox.sync_api import Camoufox

        if self._status not in ("prepared",):
            raise RuntimeError(
                f"cannot start in status {self._status!r} — call prepare() first"
            )

        self._browser = Camoufox(**self._kwargs)
        # Camoufox is a context manager: __enter__ performs the actual launch and
        # returns BrowserContext for persistent_context (Browser otherwise).
        launched = self._browser.__enter__()
        context = launched if hasattr(launched, "new_page") else launched.new_context()
        self._context = context
        self._page = context.new_page()
        self._status = "started"

        return {"status": "started", "pid": os.getpid()}

    def ready(self) -> dict[str, Any]:
        """Block until the browser is ready.

        A lightweight readiness check: if we have a page object the
        engine is considered ready (the Camoufox constructor already
        blocks until Firefox is launched and the context is created).
        """
        if self._page is None:
            return {"status": "not_ready", "reason": "no page — call start() first"}
        self._status = "ready"
        return {"status": "ready"}

    def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to *url*.

        Returns ``{"status": "ok", "url": <current>}``.
        Raises ``RuntimeError`` if page is not available.
        """
        if self._page is None:
            raise RuntimeError("no page — call start() first")

        try:
            self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
            return {"status": "ok", "url": self._page.url}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of interactive elements on the page.

        Returns ``{"status": "ok", "snapshot": {...}}``.
        For MVP: returns accessible tree snapshot as dict.
        """
        if self._page is None:
            raise RuntimeError("no page — call start() first")
        try:
            # Collect interactive elements via accessibility snapshot
            snapshot = self._page.accessibility.snapshot()
            return {"status": "ok", "snapshot": snapshot}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def screenshot(self) -> dict[str, Any]:
        """Take a screenshot of the current page.

        Returns ``{"status": "ok", "bytes": <base64>, "mime": "image/png"}``.
        """
        if self._page is None:
            raise RuntimeError("no page — call start() first")
        try:
            import base64
            png_bytes = self._page.screenshot(full_page=True)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            return {"status": "ok", "bytes": b64, "mime": "image/png"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def cookies(self) -> list[dict[str, Any]]:
        """Return current page cookies.

        Returns a list of cookie dicts.
        """
        if self._context is None:
            raise RuntimeError("no context — call start() first")
        try:
            return self._context.cookies()
        except Exception as exc:
            return [{"error": str(exc)}]

    def storage_state(self) -> dict[str, Any]:
        """Return storage state (localStorage, sessionStorage) per origin.

        Returns ``{"status": "ok", "origins": [...]}``.
        """
        if self._context is None:
            raise RuntimeError("no context — call start() first")
        try:
            state = self._context.storage_state()
            return {"status": "ok", **state}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def stop(self) -> dict[str, Any]:
        """Stop the engine and close the browser.

        Returns ``{"status": "stopped", "previous_pid": <pid>}``.
        """
        pid = os.getpid()
        try:
            if self._page is not None:
                try:
                    self._page.close()
                except Exception:
                    pass
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._browser is not None:
                try:
                    self._browser.__exit__(None, None, None)
                except Exception:
                    pass
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._status = "stopped"
        return {"status": "stopped", "previous_pid": pid}

    def __enter__(self):
        self.prepare()
        self.start()
        self.ready()
        return self

    def __exit__(self, *args):
        self.stop()
