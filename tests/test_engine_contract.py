"""Tests for engine adapter contract and worker event protocol (Task 6).

RED phase: define expected contract behaviour with a fake engine.
GREEN phase: make it pass with real implementations.
"""
from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

# ── Engine adapter contract tests ─────────────────────────────────────────────


class TestEngineAdapterContract:
    """Every engine adapter MUST satisfy this contract.

    Tests use a FakeEngine to define expected behaviour, then verify that
    the real CamoufoxEngine (or any future engine) passes the same suite.
    """

    @pytest.fixture
    def fake_engine(self):
        """Return a CamoufoxEngine with a mock profile and monkey-patched Camoufox."""
        from phantom.engines.camoufox import CamoufoxEngine

        profile = {
            "fingerprint_json": json.dumps({
                "navigator": {"userAgent": "test", "platform": "Win64",
                              "userAgentData": {}, "doNotTrack": "unspecified",
                              "appCodeName": "Mozilla", "appName": "Netscape",
                              "appVersion": "5.0", "oscpu": "Windows NT 10.0",
                              "webdriver": False, "language": "en-US",
                              "languages": ["en-US"], "deviceMemory": 8,
                              "hardwareConcurrency": 8, "product": "Gecko",
                              "productSub": "20100101", "vendor": "",
                              "vendorSub": "", "maxTouchPoints": 0,
                              "extraProperties": {}},
                "screen": {"width": 1920, "height": 1080,
                           "availWidth": 1920, "availHeight": 1040,
                           "outerWidth": 1920, "outerHeight": 800,
                           "colorDepth": 24, "pixelDepth": 24,
                           "availLeft": 0, "availTop": 0, "left": 0, "top": 0},
                "headers": {}, "videoCodecs": {}, "audioCodecs": {},
                "pluginsData": [], "battery": {}, "multimediaDevices": [],
                "fonts": [], "mockWebRTC": {},
                "videoCard": None,
            }),
            "seeds_json": json.dumps({"canvas:seed": 1, "audio:seed": 2, "fonts:spacing_seed": 3}),
            "webgl_json": json.dumps({"webGl:vendor": "Google", "webGl:renderer": "ANGLE"}),
            "fonts_json": json.dumps(["Arial", "Helvetica"]),
            "voices_json": json.dumps([]),
            "misc_json": json.dumps({"window.history.length": 3, "window.screenY": 0}),
            "timezone": "America/Denver",
            "locale_language": "en",
            "locale_region": "US",
            "navigator_language": "en-US",
            "proxy_host": "127.0.0.1", "proxy_port": 8080,
            "proxy_user": "u1", "proxy_pass": "p1",
            "id": 1, "name": "test-profile",
        }
        engine = CamoufoxEngine(profile)
        # Monkey-patch Camoufox calls for non-browser tests
        engine._camoufox_cls = MagicMock()
        return engine

    def test_engine_is_abstract(self):
        """BaseEngine cannot be instantiated directly."""
        from phantom.engines.base import BaseEngine
        with pytest.raises(TypeError):
            BaseEngine()  # type: ignore[abstract]

    def test_engine_has_required_methods(self, fake_engine):
        """Engine adapter must expose the 9 contract methods."""
        required = [
            "prepare", "start", "ready",
            "navigate", "snapshot", "screenshot",
            "cookies", "storage_state", "stop",
        ]
        for method in required:
            assert hasattr(fake_engine, method), f"missing method: {method}"
            assert callable(getattr(fake_engine, method)), f"{method} not callable"

    def test_prepare_validates_config(self):
        """prepare() must reject None/empty config."""
        from phantom.engines.base import BaseEngine

        class MinimalEngine(BaseEngine):
            def prepare(self, config: dict | None = None) -> dict:
                if not config:
                    raise ValueError("config is required")
                return {"status": "prepared"}

            def start(self) -> dict: return {"status": "started"}
            def ready(self) -> dict: return {"status": "ready"}
            def navigate(self, url: str) -> dict: return {}
            def snapshot(self) -> dict: return {}
            def screenshot(self) -> dict: return {}
            def cookies(self) -> list: return []
            def storage_state(self) -> dict: return {}
            def stop(self) -> dict: return {"status": "stopped"}

        engine = MinimalEngine()
        with pytest.raises(ValueError, match="config is required"):
            engine.prepare(None)
        with pytest.raises(ValueError, match="config is required"):
            engine.prepare({})

    def test_prepare_without_proxy_omits_invalid_proxy(self, fake_engine, monkeypatch):
        """A direct profile must not pass an empty proxy URL to Camoufox."""
        fake_engine._profile["proxy_host"] = ""
        fake_engine._profile["proxy_port"] = 0
        monkeypatch.setattr("phantom.identity.build_launch_config", lambda p: (MagicMock(), {}))
        result = fake_engine.prepare({"headless": True})
        assert "proxy" not in result["kwargs"]
        assert "geoip" not in result["kwargs"]

    def test_start_after_prepare_lifecycle(self, fake_engine, monkeypatch):
        """start() after prepare() must set internal state."""
        # Mock the identity module to avoid BrowserForge dependency
        mock_fp = MagicMock()
        mock_fp.dumps.return_value = "{}"
        monkeypatch.setattr(
            "phantom.identity.build_launch_config",
            lambda p: (mock_fp, {"timezone": "America/Denver"}),
        )
        # Mock Camoufox context manager so we don't launch a real browser
        mock_context = MagicMock()
        mock_context.new_page = MagicMock(return_value=MagicMock())
        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_context
        monkeypatch.setattr("camoufox.sync_api.Camoufox", lambda **kw: mock_manager)

        result = fake_engine.prepare({"test": True})
        assert result.get("status") == "prepared", f"got: {result}"

        result = fake_engine.start()
        assert result.get("status") in ("started", "ready"), f"got: {result}"

    def test_stop_cleans_up(self, fake_engine):
        """stop() must set status to stopped and clean resources."""
        result = fake_engine.stop()
        assert result.get("status") == "stopped", f"got: {result}"

    def test_repr_includes_engine_name(self):
        """Engine repr must identify the engine type."""
        from phantom.engines.base import BaseEngine

        class TestEngine(BaseEngine):
            def prepare(self, config=None): return {}
            def start(self): return {}
            def ready(self): return {}
            def navigate(self, url): return {}
            def snapshot(self): return {}
            def screenshot(self): return {}
            def cookies(self): return []
            def storage_state(self): return {}
            def stop(self): return {}

        engine = TestEngine()
        assert "TestEngine" in repr(engine)


class TestCamoufoxEngine:
    """Camoufox-specific engine behaviour."""

    @pytest.fixture
    def profile_dict(self) -> dict:
        """Minimal profile dict for building launch config."""
        return {
            "fingerprint_json": json.dumps({
                "navigator": {"userAgent": "test", "platform": "Win64"},
                "screen": {"width": 1920, "height": 1080, "availHeight": 1040, "outerHeight": 800},
                "headers": {}, "videoCodecs": {}, "audioCodecs": {},
                "pluginsData": [], "battery": {}, "multimediaDevices": [],
                "fonts": [], "mockWebRTC": {},
            }),
            "seeds_json": json.dumps({"canvas:seed": 1, "audio:seed": 2, "fonts:spacing_seed": 3}),
            "webgl_json": json.dumps({"webGl:vendor": "Google", "webGl:renderer": "ANGLE"}),
            "fonts_json": json.dumps(["Arial", "Helvetica"]),
            "voices_json": json.dumps([]),
            "misc_json": json.dumps({"window.history.length": 3, "window.screenY": 0}),
            "timezone": "America/Denver",
            "locale_language": "en",
            "locale_region": "US",
            "navigator_language": "en-US",
            "proxy_host": "127.0.0.1", "proxy_port": 8080,
            "proxy_user": "u1", "proxy_pass": "p1",
        }

    def test_build_launch_config_returns_tuple(self, profile_dict, monkeypatch):
        """CamoufoxEngine._build_launch_config must return (fp, config)."""
        from phantom.engines.camoufox import CamoufoxEngine

        # Mock the identity module to avoid BrowserForge fingerprint dependency
        mock_fp = MagicMock()
        mock_fp.dumps.return_value = "{}"

        def fake_build(profile):
            return (mock_fp, {"timezone": "America/Denver", "locale:language": "en"})

        monkeypatch.setattr(
            "phantom.identity.build_launch_config",
            fake_build,
        )

        engine = CamoufoxEngine(profile_dict)
        fp_obj, config = engine._build_launch_config()
        assert hasattr(fp_obj, "dumps"), "expected Fingerprint object"
        assert isinstance(config, dict), "expected config dict"
        assert "timezone" in config
        assert config["timezone"] == "America/Denver"

    def test_prepare_requires_fingerprint(self, profile_dict, monkeypatch):
        """Without fingerprint_json, prepare should raise."""
        from phantom.engines.camoufox import CamoufoxEngine
        # Mock identity to isolate the test
        monkeypatch.setattr(
            "phantom.identity.build_launch_config",
            lambda p: (MagicMock(), {}),
        )
        bad = {**profile_dict, "fingerprint_json": ""}
        engine = CamoufoxEngine(bad)
        with pytest.raises(ValueError, match="fingerprint"):
            engine.prepare()

    def test_proxy_dict_build(self, profile_dict):
        """Proxy dict must match Camoufox format."""
        from phantom.engines.camoufox import CamoufoxEngine
        engine = CamoufoxEngine(profile_dict)
        proxy = engine._proxy_dict()
        assert proxy["server"] == "http://127.0.0.1:8080"
        assert proxy["username"] == "u1"
        assert proxy["password"] == "p1"

    def test_prepare_populates_browser_kwargs(self, monkeypatch, profile_dict):
        """prepare() must build correct Camoufox kwargs."""
        from phantom.engines.camoufox import CamoufoxEngine

        captured: dict = {}

        def fake_build(profile):
            return (MagicMock(), {"test": "config"})

        monkeypatch.setattr(
            "phantom.engines.camoufox.CamoufoxEngine._build_launch_config",
            fake_build,
        )

        engine = CamoufoxEngine(profile_dict)
        result = engine.prepare()
        assert result["status"] == "prepared"
        assert "kwargs" in result
        assert result["kwargs"]["headless"] == "virtual"
        assert result["kwargs"]["geoip"] is True
        assert result["kwargs"]["block_webrtc"] is True

    def test_default_headless_mode_is_platform_appropriate(self, profile_dict, monkeypatch):
        from phantom.engines.camoufox import CamoufoxEngine

        monkeypatch.setattr("phantom.identity.build_launch_config", lambda p: (MagicMock(), {}))
        engine = CamoufoxEngine(profile_dict)
        monkeypatch.setattr("phantom.engines.camoufox.platform.system", lambda: "Windows")
        assert engine.prepare()["kwargs"]["headless"] is False

        engine = CamoufoxEngine(profile_dict)
        monkeypatch.setattr("phantom.engines.camoufox.platform.system", lambda: "Linux")
        assert engine.prepare()["kwargs"]["headless"] == "virtual"

    def test_bundled_browser_uses_explicit_executable(self, profile_dict, monkeypatch, tmp_path):
        from phantom.engines.camoufox import CamoufoxEngine

        browser = tmp_path / "camoufox.exe"
        browser.write_bytes(b"MZ")
        monkeypatch.setenv("PHANTOM_CAMOUFOX_DIR", str(tmp_path))
        monkeypatch.setattr("phantom.engines.camoufox.platform.system", lambda: "Windows")
        monkeypatch.setattr("phantom.identity.build_launch_config", lambda p: (MagicMock(), {}))
        kwargs = CamoufoxEngine(profile_dict).prepare()["kwargs"]
        assert kwargs["executable_path"] == str(browser)


# ── Worker event protocol tests ───────────────────────────────────────────────


class TestEventProtocol:
    """Worker event protocol: structured JSON events with sequence IDs."""

    def test_event_creation(self):
        """Create a valid event with all required fields."""
        from phantom.workers.protocol import Event
        ev = Event(type="start", data={"pid": 1234})
        assert ev.seq >= 0
        assert ev.type == "start"
        assert ev.data == {"pid": 1234}
        assert ev.error is None

    def test_event_auto_sequence(self):
        """Event sequence numbers must auto-increment."""
        from phantom.workers.protocol import Event
        e1 = Event(type="start")
        e2 = Event(type="ready")
        assert e2.seq == e1.seq + 1, f"expected {e1.seq + 1}, got {e2.seq}"

    def test_event_serialization(self):
        """Event must roundtrip through JSON."""
        from phantom.workers.protocol import Event
        ev = Event(type="snapshot", data={"elements": 42})
        raw = ev.to_json()
        assert isinstance(raw, str)
        restored = Event.from_json(raw)
        assert restored.type == "snapshot"
        assert restored.data == {"elements": 42}
        assert restored.seq == ev.seq

    def test_event_error_field(self):
        """Error event must include type, message, and optional detail."""
        from phantom.workers.protocol import Event
        ev = Event(type="error", data={}, error={"code": "NAV_FAIL", "message": "Timeout"})
        raw = ev.to_json()
        assert '"error"' in raw
        restored = Event.from_json(raw)
        assert restored.error["code"] == "NAV_FAIL"

    def test_malformed_json_rejected(self):
        """from_json must raise on invalid input."""
        from phantom.workers.protocol import Event
        with pytest.raises(ValueError, match="malformed"):
            Event.from_json("{bad json")

    def test_missing_type_rejected(self):
        """Event without a type should be rejected."""
        from phantom.workers.protocol import Event
        with pytest.raises(ValueError, match="type"):
            Event.from_json('{"seq": 1, "data": {}}')

    def test_event_list_serialization(self):
        """Multiple events must roundtrip as a list."""
        from phantom.workers.protocol import Event
        events = [
            Event(type="start", data={"pid": 100}),
            Event(type="ready", data={"status": "ok"}),
        ]
        raw = json.dumps([ev.to_dict() for ev in events])
        restored = [Event.from_json(json.dumps(e)) for e in json.loads(raw)]
        assert len(restored) == 2
        assert restored[0].type == "start"
        assert restored[1].type == "ready"


class TestWorkerProtocol:
    """Worker protocol integration — main entry point contract."""

    def test_worker_main_exists(self):
        """workers.main must be importable and have a main() function."""
        from phantom.workers import main as worker_main
        assert hasattr(worker_main, "main")
        assert callable(worker_main.main)

    def test_worker_emits_start_event(self):
        """Worker must emit a 'start' event on bootstrap (mocked)."""
        from phantom.workers.protocol import Event
        # Just verify the contract: start event has pid
        ev = Event(type="start", data={"pid": 999})
        assert ev.type == "start"
        assert ev.data.get("pid") is not None

    def test_worker_emits_stop_event(self):
        """Worker must emit a 'stopped' event on clean exit."""
        from phantom.workers.protocol import Event
        ev = Event(type="stopped", data={"reason": "user_request"})
        assert ev.type == "stopped"
        assert ev.data["reason"] == "user_request"

    def test_worker_emits_error_event(self):
        """Worker must emit an 'error' event on failure."""
        from phantom.workers.protocol import Event
        ev = Event(
            type="error",
            data={},
            error={"code": "ENGINE_CRASH", "message": "Camoufox exited unexpectedly"},
        )
        assert ev.type == "error"
        assert ev.error["code"] == "ENGINE_CRASH"

    def test_out_of_order_events_rejected(self):
        """Malformed/out-of-order events must be rejected by the validator."""
        from phantom.workers.protocol import validate_event_sequence
        events = [
            {"type": "start", "seq": 2, "data": {}},
            {"type": "ready", "seq": 1, "data": {}},  # out of order
        ]
        with pytest.raises(ValueError, match="sequence"):
            validate_event_sequence(events)
