from __future__ import annotations

import json

import pytest

from phantom import sidecar


@pytest.mark.parametrize(
    ("argv", "action"),
    [
        (["list"], "list"),
        (["get", "1"], "get"),
        (["create", "--name", "x", "--platform", "facebook", "--proxy", "h:1:u:p"], "create"),
        (["launch", "1"], "launch"),
        (["stop", "1"], "stop"),
        (["delete", "1"], "delete"),
        (["status", "1"], "status"),
        (["log-tail", "1"], "log-tail"),
        (["presets"], "presets"),
    ],
)
def test_all_nine_actions_have_stable_parser_entries(argv, action):
    args = sidecar.build_parser().parse_args(argv)

    assert args.action == action
    assert callable(args.handler)


def test_public_profile_redacts_proxy_password_and_identity_blobs():
    row = {
        "id": 1,
        "name": "safe",
        "proxy_pass": "secret",
        "fingerprint_json": "fp",
        "seeds_json": "seeds",
        "webgl_json": "webgl",
        "fonts_json": "fonts",
        "voices_json": "voices",
        "misc_json": "misc",
    }

    assert sidecar._public_profile(row) == {"id": 1, "name": "safe"}


def test_main_emits_success_envelope(monkeypatch, capsys):
    monkeypatch.setattr(sidecar, "action_presets", lambda args: {"presets": {}})
    parser = sidecar.build_parser()
    parser._subparsers._group_actions[0].choices["presets"].set_defaults(
        handler=lambda args: {"presets": {}}
    )
    monkeypatch.setattr(sidecar, "build_parser", lambda: parser)

    assert sidecar.main(["presets"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "data": {"presets": {}},
    }


def test_main_emits_logical_error_envelope_and_exit_zero(monkeypatch, capsys):
    parser = sidecar.build_parser()

    def fail(args):
        raise sidecar.SidecarError("not_found", "missing", {"profile": "x"})

    parser._subparsers._group_actions[0].choices["presets"].set_defaults(handler=fail)
    monkeypatch.setattr(sidecar, "build_parser", lambda: parser)

    assert sidecar.main(["presets"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "error": {
            "code": "not_found",
            "message": "missing",
            "detail": {"profile": "x"},
        },
    }


def test_bad_args_emit_json_instead_of_nonzero_exit(capsys):
    assert sidecar.main(["create"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "bad_args"
