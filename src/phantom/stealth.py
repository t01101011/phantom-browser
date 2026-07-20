"""Deterministic, offline stealth-coherence release gate.

The gate evaluates measurements, never guesses unsupported browser surfaces.  Network
geo and TLS captures are inputs produced by separate controlled probes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CONTEXTS = ("main", "worker", "shared_worker", "service_worker")
IDENTITY_KEYS = ("user_agent", "platform", "languages", "hardware_concurrency", "timezone")
_SECRET = re.compile(r"(?i)(?:https?://)?[^\s/:@]+:[^\s/@]+@|(?:token|password|authorization|proxy_url)\s*[:=]")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _major(ua: str) -> str | None:
    match = re.search(r"(?:Chrome|Chromium|Firefox)/(\d+)", ua or "")
    return match.group(1) if match else None


def redact(value: Any) -> Any:
    """Recursively remove credential-bearing values before reports are persisted."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            low = key.lower()
            if low in {"password", "token", "authorization", "proxy_url", "proxy"}:
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(x) for x in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(https?://)([^/@:]+):([^/@]+)@", r"\1[REDACTED]@", value)
    return value


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    """Return a stable verdict. Required contexts cannot be marked unsupported."""
    checks: list[dict[str, str]] = []
    def add(name: str, status: str, detail: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if report.get("schema_version") != SCHEMA_VERSION or not isinstance(report.get("runs"), list) or len(report["runs"]) < 2:
        add("schema", "fail", "schema_version=1 and at least two relaunch runs are required")
        return _verdict(checks)
    runs = report["runs"]
    add("schema", "pass")
    # Secret scan is intentionally performed on the submitted (not redacted) report.
    add("secret_redaction", "fail" if _SECRET.search(json.dumps(report)) else "pass",
        "credential/token-like material present" if _SECRET.search(json.dumps(report)) else "")

    for i, run in enumerate(runs):
        contexts = run.get("contexts", {})
        main = contexts.get("main", {})
        for context in CONTEXTS:
            measured = contexts.get(context, {})
            if measured.get("status") != "pass":
                add(f"run_{i}.{context}", "fail", "required context missing/unsupported")
                continue
            if context != "main":
                drift = [k for k in IDENTITY_KEYS if measured.get(k) != main.get(k)]
                add(f"run_{i}.{context}_coherence", "fail" if drift else "pass", ",".join(drift))

        ua = main.get("user_agent", "")
        ua_ch = run.get("ua_ch", {})
        if ua_ch.get("status") == "unsupported":
            add(f"run_{i}.ua_ch", "unsupported", ua_ch.get("reason", "not exposed by engine"))
        else:
            brands = ua_ch.get("full_versions", [])
            versions = [str(x.get("version", "")).split(".")[0] for x in brands if x.get("brand") in {"Chromium", "Google Chrome"}]
            bad = bool(_major(ua) and _major(ua) not in versions) or ua_ch.get("platform") not in ua
            add(f"run_{i}.ua_ua_ch", "fail" if bad else "pass", "UA and UA-CH disagree" if bad else "")

        gpu = run.get("gpu", {})
        add(f"run_{i}.webgl", "pass" if gpu.get("webgl", {}).get("status") == "pass" else "fail", "WebGL measurement required")
        wg = gpu.get("webgpu", {})
        if wg.get("status") == "unsupported": add(f"run_{i}.webgpu", "unsupported", wg.get("reason", "unavailable"))
        else:
            same = wg.get("adapter_class") == gpu.get("webgl", {}).get("adapter_class")
            add(f"run_{i}.gpu_coherence", "pass" if same else "fail", "WebGL/WebGPU adapter class differs" if not same else "")

        screen = run.get("screen", {})
        valid = all(isinstance(screen.get(k), int) and screen[k] > 0 for k in ("width", "height", "viewport_width", "viewport_height")) and screen["viewport_width"] <= screen["width"] and screen["viewport_height"] <= screen["height"]
        add(f"run_{i}.screen_viewport", "pass" if valid else "fail")
        geo = run.get("locale_geo", {})
        expected = geo.get("expected", {})
        observed = geo.get("observed", {})
        drift = [k for k in ("locale", "timezone", "country") if expected.get(k) is not None and expected.get(k) != observed.get(k)]
        add(f"run_{i}.locale_geo", "fail" if drift else "pass", ",".join(drift))
        fonts = run.get("fonts", {})
        add(f"run_{i}.fonts", "pass" if fonts.get("status") == "pass" and fonts.get("metrics_hash") else "fail")
        rtc = run.get("webrtc", {})
        add(f"run_{i}.webrtc", "pass" if rtc.get("status") == "pass" and not rtc.get("public_ip_leak") else "fail")
        transport = run.get("transport", {})
        for key in ("tls", "http2"):
            surface = transport.get(key, {})
            status = surface.get("status", "unsupported")
            add(f"run_{i}.{key}", status if status in {"pass", "fail", "unsupported"} else "fail", surface.get("reason", ""))

    # Relaunch determinism excludes transport and network geo by design.
    stable_paths = ("contexts", "ua_ch", "gpu", "screen", "fonts")
    drift = [p for p in stable_paths if runs[0].get(p) != runs[1].get(p)]
    add("same_profile_relaunch", "fail" if drift else "pass", ",".join(drift))
    return _verdict(checks)


def _verdict(checks: list[dict[str, str]]) -> dict[str, Any]:
    counts = {s: sum(c["status"] == s for c in checks) for s in ("pass", "fail", "unsupported")}
    # Unsupported is explicit and auditable but does not falsely become pass. TLS,
    # HTTP/2, WebGPU and UA-CH may be unavailable; required worker contexts may not.
    status = "fail" if counts["fail"] else ("conditional_pass" if counts["unsupported"] else "pass")
    return {"schema_version": SCHEMA_VERSION, "status": status, "counts": counts, "checks": sorted(checks, key=lambda c: c["name"])}


def load_and_evaluate(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    safe = redact(copy.deepcopy(raw))
    return safe, evaluate(raw)
