from pathlib import Path


WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "release-windows.yml"


def test_nsis_smoke_uses_current_user_install_location():
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text.split("- name: Install and smoke NSIS bundle", 1)[1].split(
        "- name: Generate checksums", 1
    )[0]

    assert "Join-Path $env:LOCALAPPDATA 'Phantom Browser'" in step
    assert '"/D=$install"' not in step
