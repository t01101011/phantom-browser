"""Abstract base class for browser engine adapters.

Every browser engine (Camoufox, future Chromium-based) must implement
the 9-method contract so the worker protocol and control plane can
drive it uniformly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseEngine(ABC):
    """Engine adapter contract.

    Lifecycle
    ---------
        prepare(config)  → validate config, prepare env
        start()           → launch browser
        ready()           → block until browser is ready
        navigate(url)     → go to a URL
        snapshot()        → return accessibility/DOM tree
        screenshot()      → return screenshot bytes
        cookies()         → return current cookies
        storage_state()   → return localStorage/sessionStorage/IndexedDB
        stop()            → stop browser, cleanup resources

    Each method returns a dict with at minimum ``{"status": ...}``.
    """

    @abstractmethod
    def prepare(self, config: dict | None = None) -> dict[str, Any]:
        """Validate config and prepare the engine environment.

        Raises ``ValueError`` if config is invalid.
        Returns ``{"status": "prepared", ...}``.
        """
        ...

    @abstractmethod
    def start(self) -> dict[str, Any]:
        """Start (or connect to) the browser.

        Returns ``{"status": "started" | "ready", ...}``.
        """
        ...

    @abstractmethod
    def ready(self) -> dict[str, Any]:
        """Block until the browser is fully initialised.

        Returns ``{"status": "ready", ...}``.
        """
        ...

    @abstractmethod
    def navigate(self, url: str) -> dict[str, Any]:
        """Navigate the current page to *url*.

        Returns ``{"status": "ok", "url": <current>}`` or error.
        """
        ...

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        """Return an accessibility / interactive-element snapshot.

        Returns ``{"status": "ok", "snapshot": {...}}``.
        """
        ...

    @abstractmethod
    def screenshot(self) -> dict[str, Any]:
        """Take a full-page screenshot.

        Returns ``{"status": "ok", "bytes": <base64>, "mime": "image/png"}``.
        """
        ...

    @abstractmethod
    def cookies(self) -> list[dict[str, Any]]:
        """Return browser cookies for the current page/context.

        Returns list of cookie dicts.
        """
        ...

    @abstractmethod
    def storage_state(self) -> dict[str, Any]:
        """Return current storage state (localStorage, sessionStorage).

        Returns a dict keyed by origin, each containing localStorage and
        sessionStorage key/value pairs.
        """
        ...

    @abstractmethod
    def stop(self) -> dict[str, Any]:
        """Stop the engine, close the browser, clean up resources.

        Returns ``{"status": "stopped", ...}``.
        """
        ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
