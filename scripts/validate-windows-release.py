"""Linux-safe fail-first contract checks for the native Windows release files."""
from __future__ import annotations
import ast, json, re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
def require(condition: bool, message: str) -> None:
    if not condition: errors.append(message)

workflow = (ROOT / ".github/workflows/release-windows.yml").read_text(encoding="utf-8")
spec = (ROOT / "packaging/phantom-sidecar.spec").read_text(encoding="utf-8")
smoke = (ROOT / "scripts/smoke-windows.ps1").read_text(encoding="utf-8")
conf = json.loads((ROOT / "tauri-app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
rust = (ROOT / "tauri-app/src-tauri/src/lib.rs").read_text(encoding="utf-8")
require("runs-on: windows-latest" in workflow, "workflow must use native windows-latest")
require("x86_64-pc-windows-msvc" in workflow and "windows-gnu" not in workflow, "release must use MSVC, never GNU cross-build")
for token in ("permissions:\n  contents: read", "SHA256SUMS", "smoke-windows.ps1", "phantom-sidecar.spec", "upload-artifact@v4", "downloadBootstrapper"):
    require(token in workflow or token in json.dumps(conf), f"missing release contract: {token}")
require("COLLECT(" in spec and ("camoufox.exe" in spec or "camoufox-bin.exe" in spec) and "version.json" in spec, "spec must be onedir and require browser data")
require('"apify_fingerprint_datapoints"' in spec and "collect_all(package)" in spec, "spec must collect BrowserForge's apify fingerprint datapoint archives")
require('"language_tags"' in spec and "collect_all(package)" in spec, "spec must collect language-tags JSON registry data used by BrowserForge")
for token in ("/readyz", "/v1/profiles", "/v1/sessions/instant", "taskkill.exe", "Get-CimInstance", "phantom-sidecar.exe", "Phantom Browser.exe"):
    require(token in smoke, f"smoke missing {token}")
require("$ready.status -eq 'ready'" in smoke, "smoke must accept the /readyz contract status=ready")
require("lastReadyError" in smoke and "/healthz" in smoke, "smoke timeout must report the last readiness error and public health state")
require("RedirectStandardOutput" in smoke and "RedirectStandardError" in smoke, "smoke must capture packaged sidecar stdout/stderr")
require("((Get-Content -Raw $stdoutLog) -join '').Trim()" in smoke and "((Get-Content -Raw $stderrLog) -join '').Trim()" in smoke, "smoke must read empty redirected logs without null.Trim masking the root cause")
require("Smoke packaged sidecar before desktop build" in workflow, "workflow must smoke the packaged sidecar before the expensive Tauri/NSIS build")
require(conf["bundle"]["targets"] == ["nsis"], "Tauri must build NSIS")
require(conf["bundle"]["resources"].get("../../dist/phantom-sidecar") == "phantom-sidecar", "sidecar resource mapping missing")
require("PHANTOM_PYTHON" in rust and "resources/phantom-sidecar/phantom-sidecar.exe" in rust and "taskkill" in rust, "Rust packaged discovery/cleanup missing")
for py in ("packaging/sidecar-entry.py", "packaging/pyinstaller-runtime-hook.py"):
    ast.parse((ROOT / py).read_text(encoding="utf-8"), filename=py)

archive = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if archive:
    require(archive.is_file(), f"archive not found: {archive}")
    if archive.is_file():
        with zipfile.ZipFile(archive) as z:
            names = {"/" + n.replace("\\", "/").lstrip("/") for n in z.namelist()}
            for alternatives in (("/Phantom Browser.exe",), ("/phantom-sidecar/phantom-sidecar.exe",), ("/phantom-sidecar/_internal/camoufox/camoufox.exe", "/phantom-sidecar/_internal/camoufox/camoufox-bin.exe"), ("/phantom-sidecar/_internal/camoufox/version.json",)):
                require(any(n.endswith(suffix) for n in names for suffix in alternatives), f"portable archive missing one of {alternatives}")
if errors:
    print("FAIL\n" + "\n".join(f"- {e}" for e in errors)); raise SystemExit(1)
print("PASS: Windows release static/layout contract" + (" and archive" if archive else ""))
