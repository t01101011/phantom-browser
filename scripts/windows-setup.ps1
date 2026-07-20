# Phantom Browser — Windows setup script (sidecar-only, no PyInstaller)
#
# Why a setup script instead of a bundled .exe?
#   - PyInstaller cannot cross-compile from Linux (needs Windows Python
#     runtime at build time). Building on the Lin server is impossible
#     without Wine + brittle hacks.
#   - Shipping a small, self-contained Python venv + repo clone is simpler,
#     easier to upgrade (just `git pull` + `pip install -e .`), and we can
#     keep using the same `python -m phantom.sidecar` invocation.
#   - The Tauri .exe IS cross-compiled on Linux (rustup + mingw-w64); only
#     the Python sidecar needs this script.
#
# Run this on tk's Windows machine ONCE after cloning the repo. Re-run after
# `git pull` if requirements changed.
#
# Prereqs (install manually first):
#   - Python 3.11+ from python.org (tick "Add Python to PATH")
#   - Git for Windows (optional, for `git pull` updates)
#
# Usage (PowerShell):
#   cd C:\path\to\phantom-browser
#   powershell -ExecutionPolicy Bypass -File scripts\windows-setup.ps1
#
# After this runs:
#   - .venv\ exists with camoufox[geoip] + browserforge + playwright
#   - camoufox browser binary is fetched (1.2GB, cached in %USERPROFILE%\.cache)
#   - .env is created from .env.example if not present (fill in real proxies)
#   - The Tauri app (phantom-browser.exe) can spawn `.venv\Scripts\python.exe
#     -m phantom.sidecar` when shipped in release mode.

$ErrorActionPreference = "Stop"

Write-Host "=== Phantom Browser — Windows setup ===" -ForegroundColor Cyan

# 1. Verify Python
try {
    $pyVer = python --version 2>&1
    Write-Host "Python: $pyVer"
    if ($pyVer -notmatch "3\.(11|12|13)\.") {
        Write-Warning "Recommended Python 3.11+; got $pyVer — continuing anyway"
    }
} catch {
    Write-Error "Python not found in PATH. Install Python 3.11+ from https://python.org (tick 'Add Python to PATH')."
    exit 1
}

# 2. Create venv (if missing)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv..." -ForegroundColor Yellow
    python -m venv .venv
}

# 3. Install deps
Write-Host "Installing camoufox[geoip] + browserforge + playwright..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .

# 4. Fetch camoufox browser binary (~1.2GB, cached in %USERPROFILE%\.cache)
Write-Host "Syncing + fetching camoufox browser binary (1.2GB, first run only)..." -ForegroundColor Yellow
Write-Host "  (this takes 2-5 minutes; subsequent runs skip if cached)"
.\.venv\Scripts\python.exe -m camoufox sync
.\.venv\Scripts\python.exe -m camoufox fetch

# 5. Verify install
Write-Host "Verifying camoufox install..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m camoufox version

# 6. Smoke test sidecar
Write-Host "Smoke test sidecar (should print JSON)..." -ForegroundColor Yellow
.\.venv\Scripts\python.exe -m phantom.sidecar presets | Out-String | Write-Host

# 7. .env from example
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item .env.example .env
        Write-Host "Created .env from .env.example — FILL IN real proxy creds." -ForegroundColor Yellow
    } else {
        Write-Warning "No .env and no .env.example — create .env manually with PROXY_1_HOST etc."
    }
} else {
    Write-Host ".env exists (skipped create)" -ForegroundColor Green
}

Write-Host "=== DONE ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit .env with real proxy credentials"
Write-Host "  2. Run '.\.venv\Scripts\python.exe -m phantom.cli init' to create profiles.db"
Write-Host "  3. Launch the Tauri app: phantom-browser.exe (next to where the Windows build is shipped)"
Write-Host "  4. In the app, create a profile + Launch — the GUI will spawn this venv's python"
