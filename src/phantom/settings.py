"""Settings and redaction helpers for Phantom Browser.

Provides secrets-redaction utilities for log lines, public API models,
and any place where credentials must not appear in output.
"""
from __future__ import annotations

import re
from typing import Any

# ── Regex patterns ────────────────────────────────────────────────────────────

# Proxy URLs: http://user:pass@host:port, socks5://user:pass@host:port, etc.
_PROXY_URL_RE = re.compile(
    r"(?P<scheme>https?|socks[45])://"
    r"(?P<user>[^:]+):(?P<pass>[^@]+)@",
    re.IGNORECASE,
)

# Inline tokens in query strings, headers, or config strings.
# Matches  "token=abc123" or "api_key=xyz" or "secret=xxx"
_INLINE_SECRET_RE = re.compile(
    r"(?P<key>token|api_key|apikey|secret|passwd|password)"
    r"[=:]\s*"
    r"(?P<value>[^\s\"'&,;}]+)",
    re.IGNORECASE,
)

# Well-known key names that carry secrets in dict payloads
_SECRET_KEYS = frozenset({
    "proxy_pass",
    "proxy_password",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "secret",
    "auth_token",
    "access_token",
    "refresh_token",
})

# ── Public API ────────────────────────────────────────────────────────────────


def redact_value(value: str) -> str:
    """Redact proxy passwords and inline tokens from a string.

    Use this before logging or returning data that may contain credentials.
    """
    # Redact proxy credentials in URLs:  http://user:pass@host → http://***:***@host
    value = _PROXY_URL_RE.sub(r"\g<scheme>://***:***@", value)
    # Redact inline tokens:  token=abc123 → token=*****
    value = _INLINE_SECRET_RE.sub(r"\g<key>=*****", value)
    return value


def redact_dict(d: dict) -> dict:
    """Return a shallow copy of *d* with known secret values replaced by ``"*****"``.

    Non-secret keys are passed through unchanged.
    """
    return {k: ("*****" if k in _SECRET_KEYS else v) for k, v in d.items()}


def redact_object(obj: Any) -> Any:
    """Recursively redact secrets from a nested structure.

    Walks dicts, lists, and strings to find and mask:
    - Proxy passwords embedded in URLs
    - Inline tokens / API keys
    - Dict keys whose name matches known secret field names
    """
    if isinstance(obj, dict):
        return {
            k: ("*****" if k in _SECRET_KEYS else redact_object(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_object(item) for item in obj]
    if isinstance(obj, str):
        return redact_value(obj)
    return obj
