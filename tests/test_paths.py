"""Tests for paths and settings modules."""
from __future__ import annotations

import importlib

import pytest

from phantom import paths, settings


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def test_default_data_dir_uses_platformdirs(monkeypatch):
    """When PHANTOM_DATA_DIR is not set, data_dir comes from platformdirs.

    The ``PHANTOM_DATA_DIR`` env-var is unconditionally unset because an
    earlier test fixture may have leaked it (``test_health_auth.py`` sets
    it globally).  Since ``phantom.paths`` resolves lazily via
    ``__getattr__``, simply deleting the env-var is enough — no module
    reload needed.
    """
    monkeypatch.delenv("PHANTOM_DATA_DIR", raising=False)
    from platformdirs import user_data_dir

    assert str(paths.data_dir) == user_data_dir("phantom", "phantom")


def test_data_dir_env_var_override(monkeypatch):
    """PHANTOM_DATA_DIR env var overrides the platformdirs default."""
    monkeypatch.setenv("PHANTOM_DATA_DIR", "/tmp/phantom-test-override")
    importlib.reload(paths)
    assert str(paths.data_dir) == "/tmp/phantom-test-override"


def test_profiles_dir_is_under_data_dir():
    assert paths.profiles_dir == paths.data_dir / "profiles"


def test_artifacts_dir_is_under_data_dir():
    assert paths.artifacts_dir == paths.data_dir / "artifacts"


def test_db_path_is_under_data_dir():
    assert paths.db_path == paths.data_dir / "phantom.db"


def test_runtime_dir_is_under_data_dir():
    assert paths.runtime_dir == paths.data_dir / "runtime"


def test_data_dir_is_resolved_absolute_path():
    assert isinstance(paths.data_dir, type(paths.data_dir))
    assert str(paths.data_dir).startswith("/")


def test_subdirs_are_resolved_correctly(monkeypatch):
    monkeypatch.setattr(paths, "data_dir", paths.data_dir)
    assert paths.profiles_dir.parent == paths.data_dir
    assert paths.artifacts_dir.parent == paths.data_dir
    assert paths.db_path.parent == paths.data_dir
    assert paths.runtime_dir.parent == paths.data_dir


def test_init_db_creates_platform_data_directory(tmp_path, monkeypatch):
    from phantom import db

    monkeypatch.setenv("PHANTOM_DATA_DIR", str(tmp_path / "missing"))

    db.init_db()

    assert db.DB_PATH().exists()


# ---------------------------------------------------------------------------
# Settings / Redaction
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_redact_value_removes_proxy_password_from_url(self):
        redacted = settings.redact_value("http://user:secret123@proxy.example.com:8080")
        assert "secret123" not in redacted

    def test_redact_value_handles_socks_proxy(self):
        redacted = settings.redact_value("socks5://user:passw0rd@10.0.0.1:1080")
        assert "passw0rd" not in redacted
        assert ":***@" in redacted or "*****" in redacted

    def test_redact_value_removes_token_in_query_string(self):
        redacted = settings.redact_value("https://api.example.com/path?token=abc123def&other=val")
        assert "abc123def" not in redacted

    def test_redact_value_removes_api_key(self):
        original = "api_key=sk-abc123"
        redacted = settings.redact_value(original)
        assert "sk-abc123" not in redacted

    def test_redact_value_handles_plain_text_no_secrets(self):
        assert settings.redact_value("just a normal log line without secrets") == "just a normal log line without secrets"

    def test_redact_value_handles_empty_string(self):
        assert settings.redact_value("") == ""

    def test_redact_dict_hides_secret_fields(self):
        result = settings.redact_dict({"name": "test", "proxy_pass": "s3cret", "api_key": "xyz123"})
        assert result["proxy_pass"] == "*****"
        assert result["api_key"] == "*****"
        assert result["name"] == "test"

    def test_redact_dict_preserves_non_secret_keys(self):
        d = {"name": "alpha", "status": "running", "pid": 1234}
        assert settings.redact_dict(d) == d

    def test_redact_dict_handles_empty_dict(self):
        assert settings.redact_dict({}) == {}

    def test_redact_object_nested_dict(self):
        data = {
            "profile": {"name": "alpha", "proxy_pass": "hidden"},
            "url": "http://u:secret@host:8080",
        }
        result = settings.redact_object(data)
        assert result["profile"]["proxy_pass"] == "*****"
        assert "secret@host" not in result["url"]

    def test_redact_object_list_of_dicts(self):
        data = [
            {"name": "a", "proxy_pass": "pass1"},
            {"name": "b", "proxy_pass": "pass2"},
        ]
        result = settings.redact_object(data)
        assert result[0]["proxy_pass"] == "*****"
        assert result[1]["proxy_pass"] == "*****"

    def test_redact_object_string(self):
        assert settings.redact_object("http://u:p@host") != "http://u:p@host"
        assert "p@host" not in settings.redact_object("http://u:p@host")

    def test_redact_object_non_string_non_dict(self):
        assert settings.redact_object(42) == 42
        assert settings.redact_object(None) is None
