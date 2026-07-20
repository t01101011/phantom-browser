# PyInstaller onedir specification for the authenticated Phantom control plane.
# Build from repository root after `camoufox fetch` and set PHANTOM_CAMOUFOX_DIR
# to the downloaded browser directory staged by the release workflow.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

ROOT = Path(SPECPATH).resolve().parent.parent
CAMOUFOX_BROWSER = Path(os.environ.get("PHANTOM_CAMOUFOX_DIR", ROOT / "build" / "camoufox"))
if not (CAMOUFOX_BROWSER / "version.json").is_file():
    raise SystemExit(f"Camoufox browser data missing: {CAMOUFOX_BROWSER / 'version.json'}")
if not (CAMOUFOX_BROWSER / "camoufox.exe").is_file() and not (CAMOUFOX_BROWSER / "camoufox-bin.exe").is_file():
    raise SystemExit(f"Camoufox executable missing in: {CAMOUFOX_BROWSER}")

datas = [(str(CAMOUFOX_BROWSER), "camoufox")]
binaries = []
hiddenimports = []
for package in ("camoufox", "browserforge", "playwright", "fastapi", "uvicorn", "mcp"):
    package_datas, package_bins, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_bins
    hiddenimports += package_hidden
# Metadata is required by Camoufox's compatibility/version resolver.
for distribution in ("phantom-browser", "camoufox", "browserforge", "playwright", "mcp"):
    datas += copy_metadata(distribution, recursive=True)
datas += collect_data_files("phantom", includes=["schema.sql", "migrations/*.sql"])

a = Analysis(
    [str(ROOT / "packaging" / "sidecar-entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[str(ROOT / "packaging" / "pyinstaller-runtime-hook.py")],
    excludes=["tkinter", "matplotlib", "numpy.tests", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="phantom-sidecar", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="phantom-sidecar")
