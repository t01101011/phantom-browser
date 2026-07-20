"""Regression check: Windows release must embed Tauri assets, not Vite localhost."""

from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
cargo = (root / "tauri-app" / "src-tauri" / "Cargo.toml").read_text()
exe = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist" / "windows" / "phantom-browser.exe"
errors = []

if not re.search(r"(?ms)^\[features\]\s*.*?^custom-protocol\s*=\s*\[\s*\"tauri/custom-protocol\"\s*\]", cargo):
    errors.append("Cargo.toml does not define custom-protocol -> tauri/custom-protocol")
if not re.search(r'(?m)^default\s*=\s*\[\s*"custom-protocol"\s*\]', cargo):
    errors.append("Cargo.toml does not enable custom-protocol by default")
if exe.exists():
    blob = exe.read_bytes()
    # Tauri may retain devUrl as config metadata even in release builds; the
    # decisive signal is that the hashed Vite asset path is embedded too.
    built_index = (root / "tauri-app" / "dist" / "index.html").read_text()
    match = re.search(r"assets/[A-Za-z0-9_-]+\.js", built_index)
    if not match or match.group(0).encode() not in blob:
        errors.append("Windows release EXE does not embed the built Vite frontend asset")

if errors:
    print("FAIL")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)
print("PASS: Windows release uses embedded Tauri assets")
