import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-windows.yml"
TAURI_CONFIG = ROOT / "tauri-app" / "src-tauri" / "tauri.conf.json"


def test_nsis_main_binary_matches_smoke_contract():
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))

    assert config["mainBinaryName"] == "Phantom Browser"


def test_portable_stage_copies_configured_main_binary():
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split("- name: Stage and smoke portable layout", 1)[1].split(
        "- name: Install and smoke NSIS bundle", 1
    )[0]

    source = (
        "tauri-app\\src-tauri\\target\\x86_64-pc-windows-msvc\\release\\"
        f'{config["mainBinaryName"]}.exe'
    )
    assert source in step
    assert "release\\tauri-app.exe" not in step


def test_nsis_smoke_uses_current_user_install_location():
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split("- name: Install and smoke NSIS bundle", 1)[1].split(
        "- name: Generate checksums", 1
    )[0]

    assert "Join-Path $env:LOCALAPPDATA 'Phantom Browser'" in step
    assert '"/D=$install"' not in step
