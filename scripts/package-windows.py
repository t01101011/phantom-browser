"""Retired legacy GNU/raw-source Windows packager.

Native releases are built and smoke-tested exclusively by
.github/workflows/release-windows.yml on windows-latest (MSVC + PyInstaller
onedir + Tauri NSIS). This script intentionally fails so an untested GNU
cross-build cannot be mistaken for a release.
"""
raise SystemExit(
    "Legacy package-windows.py is retired; dispatch release-windows.yml on "
    "windows-latest. Native Windows CI acceptance is mandatory."
)
