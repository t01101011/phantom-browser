from __future__ import annotations

import importlib.util
from pathlib import Path


PROBE = Path(__file__).parents[2] / "spikes" / "chromium-engine" / "probe.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("chromium_engine_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expected_schema_covers_acceptance_surfaces():
    probe = load_probe()
    assert probe.SCHEMA_VERSION == 1
    assert set(probe.SURFACE_KEYS) >= {
        "ua_ua_ch",
        "worker_main",
        "webgl_webgpu",
        "fonts",
        "canvas_audio_client_rects",
        "webrtc_dns",
        "tls_http2",
    }


def test_canonical_checksum_ignores_checksum_field():
    probe = load_probe()
    report = {"schema_version": 1, "candidate": "stock", "checksum_sha256": "old"}
    first = probe.report_checksum(report)
    report["checksum_sha256"] = "different"
    assert probe.report_checksum(report) == first
    assert len(first) == 64
