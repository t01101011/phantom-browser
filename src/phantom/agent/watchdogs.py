"""Page lifecycle watchdog event adapters."""
from __future__ import annotations
from typing import Any, Callable


def install_watchdogs(page: Any, emit: Callable[[str, dict], None]) -> None:
    """Translate Playwright lifecycle callbacks to compact, non-secret events."""
    if not hasattr(page, "on"):
        return
    page.on("popup", lambda popup: emit("page.popup", {"url": getattr(popup, "url", "")}))
    page.on("download", lambda download: emit("page.download", {"suggested_filename": getattr(download, "suggested_filename", "")}))
    page.on("crash", lambda *args: emit("page.crash", {"code": "PAGE_CRASHED"}))
