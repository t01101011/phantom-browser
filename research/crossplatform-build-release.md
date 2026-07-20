# Nghiên cứu Cross-Platform Build/Release cho Antidetect Desktop + Service

**Ngày**: 2026-07-19  
**Mục đích**: Cập nhật kế hoạch cho Phantom Tauri+React+Python sidecar (đã fail Windows packaging)  
**Yêu cầu**: Chỉ research, không code changes

---

## Mục lục

1. [Tổng quan hệ sinh thái — Audit 4 Repo thực tế](#1-tổng-quan-hệ-sinh-thái--audit-4-repo-thực-tế)
2. [So sánh Desktop Framework: Tauri vs Electron vs pywebview](#2-so-sánh-desktop-framework-tauri-vs-electron-vs-pywebview)
3. [PyInstaller + Camoufox Packaging Patterns](#3-pyinstaller--camoufox-packaging-patterns)
4. [Windows CI Runners (GitHub Actions)](#4-windows-ci-runners-github-actions)
5. [Linux Packaging: AppImage/deb/systemd/Docker/Xvfb/Wayland](#5-linux-packaging-appimagedebsystemddockerxvfbwayland)
6. [Process Cleanup: Job Objects vs cgroups](#6-process-cleanup-job-objects-vs-cgroups)
7. [Release Smoke Tests](#7-release-smoke-tests)
8. [Khuyến nghị dựa trên bằng chứng (Evidence-Based)](#8-khuyến-nghị-dựa-trên-bằng-chứng-evidence-based)
9. [Build/Test Patterns chính xác](#9-buildtest-patterns-chính-xác)

---

## 1. Tổng quan hệ sinh thái — Audit 4 Repo thực tế

### 1.1 Donut Browser (zhom/donutbrowser) ⭐3.4k

| Thuộc tính | Giá trị |
|---|---|
| **Stack** | **Tauri 2.x** (Rust backend) + **Next.js** (TypeScript) frontend |
| **Engine** | Wayfern (Chromium fork tự privacy), đã deprecate Camoufox từ v0.28 |
| **Bundle targets** | `.dmg` (macOS), `.exe`/NSIS (Windows), `.deb`/`.rpm`/`.AppImage` (Linux) |
| **CI/CD** | GitHub Actions, `release.yml` 647 lines: matrix build 5 platform |
| **Sidecar** | Rust binary `donut-proxy` build riêng + copy vào `src-tauri/binaries/` |
| **Linux deps** | `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev` |
| **Update** | Tauri built-in updater + SHA256SUMS + delta updates |
| **Đáng chú ý** | Dùng `tauri-apps/tauri-action@v1.0.0` để build; portable ZIP riêng cho Windows |

**Pattern CI/CD chính**:
- Matrix: 5 runners (macOS arm64/x64, Ubuntu 22.04 x64/arm64, Windows latest)
- Build frontend `pnpm exec next build` riêng
- Build sidecar Rust binary riêng với `cargo build --bin donut-proxy`
- Copy sidecar vào `src-tauri/binaries/` với target-triple suffix
- Tauri action tự động gọi `pnpm tauri build` → ra `.deb`/`.rpm`/`.AppImage`
- Job `checksums` tạo SHA256SUMS.txt từ artifacts đã upload
- Job `changelog` tự động generate + squash merge PR docs

### 1.2 FoxDesk (BB0813/foxdesk) ⭐3

| Thuộc tính | Giá trị |
|---|---|
| **Stack** | **pywebview** (Python) + **FastAPI** backend + vanilla JS frontend |
| **Desktop shell** | pywebview → Windows WebView2 |
| **Engine** | Camoufox (Firefox fork) + Chromium/Patchright (dual-engine Phase C) |
| **Packaging** | PyInstaller (foxdesk.spec) + Inno Setup (installer.iss) |
| **CI/CD** | GitHub Actions `build.yml` 255 lines, Windows-only |
| **Smoke test** | `--worker missing-runtime.json` check exit code; verify bundled camoufox + apify datapoints |
| **Volume** | Portable ~394 MB, Setup ~69.8 MB (sau khi exclude torch/jedi) |

**Điểm đặc biệt**:
- `foxdesk.spec` dùng `collect_all()` cho camoufox, browserforge, apify_fingerprint_datapoints, playwright, patchright, pythonnet
- `excludes = ['torch', 'scipy', 'pandas', 'jedi', 'IPython', ...]` — rất quan trọng (dính 471MB torch)
- Inno Setup `PrivilegesRequired=lowest` — cài vào `%LOCALAPPDATA%\Programs\FoxDesk`
- `installer.iss` có `taskkill` dọn process trước khi uninstall/upgrade
- Smoke test dùng `Start-Process` với timeout 30s, verify camoufox/pkgman.py + apify datapoint zips
- Portable `.zip` build manual; release có `SHA256SUMS` cho in-app update

### 1.3 CamouFlow (Tort1k558/Camouflow) ⭐13

| Thuộc tính | Giá trị |
|---|---|
| **Stack** | **PyQt6/QML** (Python) + Camoufox/CloakBrowser |
| **Packaging** | PyInstaller (camouflow.spec), build.bat đơn giản |
| **CI/CD** | GitHub workflow chỉ có cloud workspace integration, chưa có build pipeline |
| **Data** | Lưu local profiles/scenarios/proxies, không bundle browser cache |
| **Đáng chú ý** | `build.bat` chỉ 21 lines — taskkill + PyInstaller đơn giản; không smoke test CI |

### 1.4 BrowseForge

Repository đã xác minh: https://github.com/nczz/BrowseForge. Đây là Go local service với REST API, MCP Streamable HTTP, web dashboard và multi-runtime Camoufox/CloakBrowser. Nó hữu ích cho control-plane/agent patterns, nhưng không phải reference chính cho Tauri packaging; phần release cần audit riêng theo tag/artifact hiện hành.

---

## 2. So sánh Desktop Framework: Tauri vs Electron vs pywebview

### Bảng so sánh chính (dữ liệu benchmark thực tế từ Elanis/web-to-desktop-framework-comparison + Tech Insider 2026)

| Tiêu chí | Tauri 2.x | Electron 43.x | pywebview |
|---|---|---|---|
| **Engine** | OS native WebView (WebView2/WKWebView/WebKitGTK) | Bundled Chromium 150 | OS native WebView |
| **Backend** | Rust | Node.js 24 | Python |
| **Bundle size (empty app)** | ~3-4 MB | ~85-374 MB | ~15-50 MB (with Python runtime) |
| **Idle RAM (release)** | ~19-95 MB | ~64-632 MB | ~30-100 MB (est.) |
| **Cold start (release)** | ~645-1316 ms | ~182-297 ms | ~300-800 ms (est.) |
| **Build time (Windows x64)** | ~248s (Rust compile) | ~5s | ~30-60s (PyInstaller) |
| **Cross-platform** | Win/Mac/Linux/iOS/Android | Win/Mac/Linux | Win/Mac/Linux |
| **GPU/WebGL** | Via WebView | Full Chromium GPU stack | Via WebView2 |
| **Native API access** | Rust plugins (capability-based) | Node.js native modules | Python ctypes/cffi |
| **Auto-updater** | Built-in + delta updates | electron-updater (community) | Custom implementation needed |
| **Sidecar support** | `externalBin` config (Rust/any) | Child process via Node | Python subprocess |
| **Security model** | Capability-based (opt-in) | Permissive (opt-out) | OS-level + Python sandbox |
| **Ecosystem maturity** | Growing (~109k GitHub stars) | Very mature (~122k stars) | Niche (~3.5k stars) |
| **Rust learning curve** | Required for backend | None (JS/TS) | None (Python) |

### Phân tích cho use case Antidetect Desktop + Service

#### Tauri ✅ **Khuyến nghị cho Phantom**
- **Ủng hộ**: Bundle nhỏ (3-15 MB), Rust backend safety, `externalBin` cho Python sidecar, Tauri 2.x built-in updater, capability security model
- **Đã chứng minh**: Donut Browser dùng Tauri thành công cho antidetect browser với 3.4k stars
- **Rủi ro**: Windows packaging đã fail (cần fix sidecar binary path); Rust compile chậm; WebView không dùng được cho headless service
- **Linux headless**: Tauri app cần display (Xvfb hoặc xvfb-run); không chạy native headless

#### Electron ❌
- **Quá nặng**: 85-374 MB base; 100-632 MB RAM — không phù hợp antidetect khi browser đã nặng
- **Security**: Chromium attack surface lớn; Node.js IPC security issues
- **Không mobile**: Trong khi Tauri đã có iOS/Android

#### pywebview ✅ **Khuyến nghị cho Windows-first MVP**
- **Ủng hộ**: Python native, PyInstaller packaging đã được FoxDesk chứng minh, WebView2 nhẹ
- **Đã chứng minh**: FoxDesk (v1.4.0) dùng pywebview + FastAPI, đã ship Windows thành công với CI/CD
- **Rủi ro**: Linux cần WebKitGTK; không built-in auto-updater; ecosystem nhỏ
- **Hạn chế headless**: Giống Tauri, cần display server

### Quyết định: **Giữ Tauri + React + Python sidecar** (đã chọn)
> Lý do: Donut Browser đã chứng minh pattern này thành công. Vấn đề Windows packaging cần sửa chứ không phải đổi framework.

---

## 3. PyInstaller + Camoufox Packaging Patterns

### Pattern từ FoxDesk (đã chạy production)

**foxdesk.spec** — những điểm quan trọng:

```python
# 1. Hidden imports cực kỳ quan trọng cho Camoufox
hiddenimports = [
    'camoufox', 'camoufox.sync_api', 'camoufox.async_api',
    'camoufox.server', 'camoufox.utils', 'camoufox.fingerprints',
    'camoufox.pkgman', 'camoufox.addons', 'camoufox.locale',
    'camoufox.ip', 'camoufox.webgl',
    'browserforge', 'browserforge.fingerprints', 'browserforge.headers',
    'browserforge.download', 'browserforge.bayesian_network',
    'apify_fingerprint_datapoints',
    'playwright', 'playwright.sync_api', 'playwright.async_api',
]

# 2. Dùng collect_all() cho package có data files
for pkg in ('camoufox', 'browserforge', 'apify_fingerprint_datapoints',
            'playwright', 'patchright', 'pythonnet'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)

# 3. Exclude ML/IDE packages (CỰC KỲ QUAN TRỌNG)
excludes = [
    'torch', 'torchvision', 'transformers', 'scipy', 'pandas',
    'jedi', 'IPython', 'matplotlib', 'sklearn', 'tensorflow',
    'keras', 'mypy', 'pytest', 'black', 'ruff',
]
```

**Vấn đề đã gặp** (từ build-release-notes.md FoxDesk):
- **Volume**: Lần đầu PyInstaller build ra ~1.5 GB vì host site-packages có torch (471 MB) + jedi (335 MB)
- **Sửa**: Thêm `excludes` list → portable **~394 MB**, Setup **~69.8 MB**
- **Camoufox data**: `camoufox.pkgman` và `apify_fingerprint_datapoints/data/*.zip` cần collect riêng
- **pythonnet**: WebView2 WinForms backend cần full pythonnet runtime DLLs

### Pattern từ CamouFlow (đơn giản hơn)

```python
# camouflow.spec — đơn giản, dùng collect_data_files + collect_submodules
datas += collect_data_files("camoufox")
hiddenimports += collect_submodules("camoufox")
# Tương tự cho cloakbrowser, browserforge, language_tags
```

### Khuyến nghị cho Phantom:
1. **Bắt buộc `excludes`** — chặn torch, tensorflow, scipy, pandas, matplotlib, jedi, IPython
2. **`collect_all('camoufox')`** — đảm bảo đủ data files
3. **`collect_all('playwright')`** — nếu dùng Playwright
4. **Không bundle browser binary** — để user download riêng (playwright install)
5. **CI smoke test** — verify binary chạy được + import đúng (pattern FoxDesk)

---

## 4. Windows CI Runners (GitHub Actions)

### Phân tích từ Donut Browser release.yml

```yaml
# Matrix build cho Windows
- platform: "windows-latest"
  args: "--target x86_64-pc-windows-msvc --verbose"
  arch: "x86_64"
  target: "x86_64-pc-windows-msvc"
```

**Điểm chính**:
- Dùng `windows-latest` (Windows Server 2022+)
- MSVC target (không GNU)
- Tauri action tự động sign Windows executable (nếu có cert)
- Portable ZIP: copy `donutbrowser.exe` + `donut-proxy.exe` + WebView2Loader.dll
- NSIS installer được tạo bởi `tauri-apps/tauri-action`

### Phân tích từ FoxDesk build.yml

```yaml
# FOXDESK Windows CI pattern (Windows-only)
build-windows:
  runs-on: windows-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: 'pip'
    - run: python -m pip install -r requirements.txt
    - run: python -m compileall backend desktop.py  # Syntax check
    - run: python -m pytest tests -q --tb=short      # Unit tests
    - run: python -m PyInstaller foxdesk.spec --noconfirm --clean --log-level WARN
    - run: choco install innosetup -y --no-progress    # Inno Setup via Chocolatey
    - run: ISCC.exe installer.iss                      # Build installer
    - name: Smoke test frozen binary
      shell: pwsh
      run: |
        $p = Start-Process -FilePath "dist/FoxDesk/FoxDesk.exe" `
          -ArgumentList @('--worker', 'missing-runtime.json') `
          -PassThru -WindowStyle Hidden
        if (-not $p.WaitForExit(30000)) { throw "timeout" }
        # Verify bundled packages
```

**Điểm chính cho Windows**:
- `windows-latest` có sẵn Python + Chocolatey
- Chạy `python -m compileall` để check syntax errors
- **Smoke test frozen binary**: chạy `--worker` mode với missing runtime → verify exit code ≠ 0
- **Verify bundled packages**: dùng PowerShell Get-ChildItem check camoufox/pkgman.py
- **Choco install innosetup** — nhanh hơn winget cho CI
- **SHA256SUMS** được tạo trong release job

### Khuyến nghị cho Phantom:
1. Dùng `windows-latest` — đủ dùng cho MSVC build
2. Thêm `windows-2022` cụ thể nếu cần SDK cũ
3. **Không** dùng self-hosted runner trừ khi cần GPU đặc biệt
4. **Cache**: `actions/cache@v4` cho `~/.cache/ms-playwright` và `~/.cargo`
5. **Python cache**: `actions/setup-python@v5` với `cache: 'pip'`
6. **Rust cache**: `swatinem/rust-cache@v2` với `workdir: ./src-tauri`

---

## 5. Linux Packaging: AppImage/deb/systemd/Docker/Xvfb/Wayland

### Donut Browser pattern (Tauri)

```yaml
# Tauri.conf.json bundle targets
"bundle": {
  "targets": ["app", "dmg", "nsis", "deb", "rpm", "appimage"],
  "linux": {
    "deb": {
      "depends": ["xdg-utils", "libxdo3", "libayatana-appindicator3-1"]
    }
  }
}
```

Tauri bundle tự động tạo:
- `.deb` cho Debian/Ubuntu
- `.rpm` cho Fedora/RHEL
- `.AppImage` portable
- Nix flake (có CI job `update-flake` tự động update hashes)

**Linux deps** cần trên runner:
```bash
sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev \
  libayatana-appindicator3-dev librsvg2-dev libxdo-dev pkg-config xdg-utils
```

### Phân tích cho headless/service mode

| Approach | Ưu điểm | Nhược điểm |
|---|---|---|
| **Xvfb** | Đơn giản, works với mọi app cần display | ~10-30 MB RAM, cần xvfb-run wrapper |
| **Wayland** (headless) | Modern, native Linux | Chưa phổ biến trên server; Weston composition |
| **Docker** (standalone) | Isolated, reproducible | Cần display server trong container; volume mounts |
| **systemd service** | Auto-restart, logging, cgroups | Cần user service, display env setup |
| **Direct headless** (Playwright) | Không cần display | Chỉ cho automation (headed browser vẫn cần display) |

**Pattern khuyến nghị cho Linux service**:
1. AppImage hoặc .deb cho desktop component
2. Docker image cho headless service component (với Xvfb built-in)
3. systemd user service cho background worker
4. Script wrapper `phantom-linux.sh` phát hiện display:

```bash
#!/bin/bash
# phantom-linux.sh
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    if command -v Xvfb &> /dev/null; then
        export DISPLAY=:99
        Xvfb :99 -screen 0 1280x720x24 &
        XVFB_PID=$!
        trap "kill $XVFB_PID" EXIT
    elif [ -n "$(command -v xvfb-run)" ]; then
        exec xvfb-run "$@"
    else
        echo "ERROR: No display server found. Install xvfb-run."
        echo "sudo apt install xvfb"
        exit 1
    fi
fi
exec "$@"
```

**Docker pattern**:
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y \
    libwebkit2gtk-4.1-dev xvfb libgtk-3-dev \
    libayatana-appindicator3-dev, python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
ENV DISPLAY=:99
COPY phantom /opt/phantom
ENTRYPOINT ["xvfb-run", "/opt/phantom/phantom-service"]
```

---

## 6. Process Cleanup: Job Objects vs cgroups

### Windows: Job Objects

**Pattern từ FoxDesk installer.iss**:
```pascal
// Dùng taskkill /F /IM FoxDesk.exe /T trước khi uninstall
Exec('taskkill.exe', '/F /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
```

**Pattern khuyến nghị cho Phantom** (Python sidecar):
```python
# Windows: Job Object API
import win32api, win32con, win32job

def create_job(name="PhantomJob"):
    h_job = win32job.CreateJobObject(None, name)
    info = win32job.QueryInformationJobObject(h_job,
        win32job.JobObjectBasicLimitInformation)
    info['LimitFlags'] = win32con.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(h_job,
        win32job.JobObjectBasicLimitInformation, info)
    return h_job

def assign_process_to_job(h_job, pid):
    win32job.AssignProcessToJobObject(h_job, win32api.OpenProcess(
        win32con.PROCESS_ALL_ACCESS, False, pid))
```

**Cách hoạt động**:
- `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`: Khi job handle bị close, **tất cả** process trong job bị kill
- Phù hợp cho: sidecar processes, browser workers, child browser instances
- Không cần tracking từng child process
- `taskkill /T` cũng kill tree, nhưng không reliable như Job Object

### Linux: cgroups v2

**Pattern cgroups v2 cho process tree cleanup**:

```python
# Linux: systemd-run để tạo transient scope
import subprocess

def start_in_cgroup(cmd, name="phantom-worker"):
    """Start process in dedicated cgroup via systemd-run"""
    return subprocess.Popen([
        'systemd-run', '--user', '--scope',
        f'--unit={name}',
        '--property=KillMode=control-group',
        '--property=TasksMax=100',
        *cmd
    ])

# Tự động cleanup: systemd kill toàn bộ scope
# Có thể dùng: systemctl --user stop phantom-worker.scope
```

**Pattern tay** (không systemd):
```python
# Linux: Process group kill
import os, signal

def start_process_group(cmd):
    return subprocess.Popen(cmd, preexec_fn=os.setsid)

def kill_process_group(proc):
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    # Sau 5s nếu chưa chết:
    # os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
```

### So sánh cross-platform:

| Cơ chế | Windows | Linux | macOS |
|---|---|---|---|
| **Tree kill** | `taskkill /T` | `kill -TERM -pid` | `kill -TERM -pid` |
| **Kill-on-close** | Job Objects (`KILL_ON_JOB_CLOSE`) | ⚠️ prctl(PR_SET_PDEATHSIG) | ⚠️ NSTask |
| **System managed** | — | systemd scopes | launchd |
| **Resource limits** | Job Objects ULIMIT | cgroups v2 | — |
| **Recommended** | **Job Objects** | **systemd scopes** | Process group |

**Khuyến nghị cho Phantom**:
- **Windows**: Dùng Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) — đây là cách duy nhất đảm bảo cleanup khi crash
- **Linux**: Dùng `systemd-run --user --scope` + `KillMode=control-group` hoặc `os.setsid()` + `killpg()`
- Cross-platform wrapper: dùng `psutil` để kill process tree (phòng khi Job Object không hoạt động)

---

## 7. Release Smoke Tests

### Pattern FoxDesk (Windows, PyInstaller)

```yaml
# CI smoke test steps
# 1. Syntax check
- run: python -m compileall backend desktop.py
- run: node --check static/app.js

# 2. Unit tests
- run: python -m pytest tests -q --tb=short

# 3. Smoke test frozen binary
- name: Smoke test frozen CLI flags
  shell: pwsh
  run: |
    $exe = "dist/FoxDesk/FoxDesk.exe"
    # Test --worker với missing runtime → fail nhanh
    $p = Start-Process -FilePath $exe -ArgumentList @('--worker', 'missing-runtime.json') `
      -PassThru -WindowStyle Hidden
    if (-not $p.WaitForExit(30000)) { throw "worker smoke test timed out" }
    if ($p.ExitCode -eq 0) { throw "expected non-zero exit for missing runtime" }

    # Verify bundled packages
    $camoufoxDir = Get-ChildItem "dist/FoxDesk" -Recurse -Directory -Filter "camoufox" | Select-Object -First 1
    if (-not $camoufoxDir) { throw "camoufox package directory missing" }
    $pkgman = Join-Path $camoufoxDir.FullName "pkgman.py"
    if (-not (Test-Path $pkgman)) { throw "camoufox/pkgman.py missing" }
```

### Pattern FoxDesk (manual pre-release)

```markdown
# Smoke checklist (từ build-release-notes.md)
1. Install/run FoxDesk → window + local API ok
2. System page → app_version = X.X.X
3. Camoufox Install/Fetch
4. Create template profile → success
5. Launch profile → ready log
6. Deliberately uninstall browser → error message
7. Export diagnostics → no secret keys
```

### Pattern Donut Browser (Tauri, cross-platform)

```yaml
# release.yml — các job trước release:
jobs:
  security-scan:  # OSV scanner
  lint-js:        # ESLint/Biome
  lint-rust:      # Clippy
  codeql:         # CodeQL analysis
  spellcheck:     # Typos check
  release:        # Chỉ chạy sau khi all gates pass
```

### Khuyến nghị cho Phantom:

```yaml
# CI Smoke Test Pipeline
smoke-tests:
  strategy:
    matrix:
      os: [windows-latest, ubuntu-22.04]
  steps:
    # 1. Unit tests (Python + Rust)
    - run: python -m pytest tests/ -q
    - run: cargo test --manifest-path src-tauri/Cargo.toml

    # 2. Build sidecar + verify version
    - run: python build_sidecar.py --verify

    # 3. PyInstaller/Tauri build smoke
    - run: |
        # Windows: test --service mode
        ./dist/Phantom/Phantom.exe --service --port 8765 &
        sleep 5
        curl -f http://127.0.0.1:8765/health || exit 1
        kill %1

    # 4. Verify bundled packages (Windows)
    - if: matrix.os == 'windows-latest'
      run: |
        python -c "
        import sys; sys.path.insert(0, 'dist/Phantom/_internal')
        import camoufox; print('camoufox OK')
        import browserforge; print('browserforge OK')
        "

    # 5. Linux: smoke headless service with Xvfb
    - if: matrix.os == 'ubuntu-22.04'
      run: |
        xvfb-run -a ./dist/Phantom/Phantom --service &
        sleep 5
        curl -f http://127.0.0.1:8765/health || exit 1
```

---

## 8. Khuyến nghị dựa trên bằng chứng (Evidence-Based)

### 8.1 Framework: **Giữ Tauri 2.x** (không đổi sang Electron hay pywebview)

**Căn cứ**:
- Donut Browser ⭐3.4k đã chứng minh Tauri + React + Rust sidecar hoạt động production cho antidetect
- Tauri bundle **3-15 MB** vs Electron **85-374 MB** — critical cho antidetect khi browser đã nặng
- Tauri security model (capability-based) phù hợp antidetect use case
- Windows packaging fail là do lỗi cấu hình, không phải lỗi framework

### 8.2 Windows Packaging: **Sửa PyInstaller/Tauri config**

**Vấn đề**:
- Tauri + Python sidecar dùng `externalBin` config
- PyInstaller đóng gói Python code → gọi từ Rust Tauri backend
- Windows fail có thể do: (1) sidecar binary path sai, (2) thiếu DLL dependencies, (3) pythonnet không collect đúng

**Giải pháp từ FoxDesk**:
- Dùng `foxdesk.spec` pattern với `collect_all('pythonnet')`
- Exclude ML/IDE packages để tránh volume explosion
- Smoke test với `--worker` flag trước khi release

### 8.3 Linux Packaging: **AppImage cho desktop + Docker cho service**

**Căn cứ**:
- Tauri có built-in AppImage/deb/rpm support — Donut Browser dùng
- AppImage dễ portable, không cần root
- Docker + Xvfb cho headless service mode đã được chứng minh trong ecosystem
- script wrapper `xvfb-run` là pattern đơn giản nhất cho headless

### 8.4 Process Cleanup: **Job Objects (Windows) + systemd scopes (Linux)**

**Căn cứ**:
- `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` là cơ chế duy nhất trên Windows đảm bảo cleanup khi crash
- systemd `KillMode=control-group` đảm bảo cleanup trên Linux
- FoxDesk dùng `taskkill /T` nhưng đây không phải reliable solution cho crash scenarios

### 8.5 CI/CD: **GitHub Actions matrix build**

**Căn cứ**:
- Donut Browser dùng 5 platform matrix build thành công
- FoxDesk dùng `windows-latest` + Chocolatey cho Inno Setup
- Cần thêm `swatinem/rust-cache@v2` cho Rust compile time

### 8.6 Smoke Tests: **Pre-release checklist + CI automation**

**Căn cứ**:
- FoxDesk có smoke test chi tiết trong `build-release-notes.md`
- Donut Browser có security-scan + lint gates trước release
- Cần kết hợp cả 2 pattern: CI automated + manual pre-release checklist

---

## 9. Build/Test Patterns chính xác

### Pattern A: Tauri + Rust Sidecar (Donut Browser) — CHO PHANTOM

```yaml
# .github/workflows/release.yml — matrix build
name: Release Phantom
on:
  push:
    tags: ["v*"]
env:
  TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
  TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}

jobs:
  # ... security-scan, lint-js, lint-rust, codeql, spellcheck gates ...
  
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - platform: "windows-latest"
            target: "x86_64-pc-windows-msvc"
          - platform: "ubuntu-22.04"
            target: "x86_64-unknown-linux-gnu"
    runs-on: ${{ matrix.platform }}
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - uses: actions/setup-node@v4
        with:
          node-version-file: .node-version
          cache: "pnpm"
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      
      # Linux deps
      - if: matrix.platform == 'ubuntu-22.04'
        run: sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev \
          libayatana-appindicator3-dev librsvg2-dev libxdo-dev pkg-config xdg-utils
      
      - uses: swatinem/rust-cache@v2
        with:
          workdir: ./src-tauri
      
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
      
      # Build Python sidecar
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt pyinstaller
      - run: pyinstaller sidecar.spec --noconfirm --clean --log-level WARN
      
      # Copy sidecar to Tauri binaries
      - run: |
          mkdir -p src-tauri/binaries
          cp dist/sidecar/sidecar.exe src-tauri/binaries/sidecar-x86_64-pc-windows-msvc.exe
      
      # Build Tauri app
      - uses: tauri-apps/tauri-action@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          projectPath: ./src-tauri
          tagName: ${{ github.ref_name }}
          releaseName: "Phantom ${{ github.ref_name }}"
          args: "--target ${{ matrix.target }}"
      
      # Windows portable ZIP
      - if: matrix.platform == 'windows-latest'
        run: |
          7z a Phantom-${{ github.ref_name }}-x64-portable.zip \
            src-tauri/target/${{ matrix.target }}/release/*.exe
```

### Pattern B: Python Sidecar PyInstaller Spec (FOXDESK pattern)

```python
# sidecar.spec — cho Phantom Python sidecar
from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path

ROOT = Path(SPECPATH)

# === DATA ===
datas = []
binaries = []
hiddenimports = []

# === CAMOUFOX ===
for pkg in ('camoufox', 'browserforge', 'apify_fingerprint_datapoints',
            'playwright', 'certifi'):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

# === CRITICAL EXCLUDES ===
excludes = [
    'torch', 'torchvision', 'transformers', 'tensorflow', 'tensorboard',
    'scipy', 'pandas', 'numpy', 'numba', 'llvmlite', 'matplotlib',
    'sklearn', 'jedi', 'IPython', 'ipykernel', 'notebook',
    'mypy', 'pytest', 'black', 'isort', 'ruff',
    'cv2', 'tensorflow', 'keras',
]

a = Analysis(
    ['sidecar_main.py'],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True,
          name='PhantomSidecar', console=False, upx=True)
coll = COLLECT(exe, a.binaries, a.datas, name='PhantomSidecar')
```

### Pattern C: Process Cleanup (Cross-platform)

```python
# process_cleanup.py
import os
import sys
import signal
import subprocess

def create_process_group():
    """Windows: tạo Job Object • Linux: setsid"""
    if sys.platform == 'win32':
        return _create_win32_job()
    else:
        # Linux/Mac: process group sẽ tự động cleanup
        return None

def _create_win32_job():
    """Tạo Windows Job Object với KILL_ON_JOB_CLOSE"""
    import win32api, win32con, win32job
    h_job = win32job.CreateJobObject(None, None)
    info = win32job.QueryInformationJobObject(
        h_job, win32job.JobObjectBasicLimitInformation)
    info['LimitFlags'] |= win32con.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(
        h_job, win32job.JobObjectBasicLimitInformation, info)
    return h_job

def launch_worker(cmd, job=None):
    """Launch process, attach to job/group"""
    if sys.platform == 'win32':
        proc = subprocess.Popen(cmd)
        if job:
            import win32api, win32con, win32job, pywintypes
            try:
                h_process = win32api.OpenProcess(
                    win32con.PROCESS_ALL_ACCESS, False, proc.pid)
                win32job.AssignProcessToJobObject(job, h_process)
            except pywintypes.error:
                pass
        return proc
    else:
        # Linux: process group
        return subprocess.Popen(cmd, preexec_fn=os.setsid)

def kill_process_tree(proc):
    """Kill toàn bộ process tree"""
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                      capture_output=True)
    else:
        # Linux/Mac: kill process group
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
```

### Pattern D: Linux Headless Service Launcher

```bash
#!/bin/bash
# phantom-service.sh — Linux headless launcher
set -euo pipefail

APP_DIR="$(dirname "$(readlink -f "$0")")"

# === Display setup ===
ensure_display() {
    if [ -n "${DISPLAY:-}" ]; then
        return 0  # Already have a display
    fi
    if [ -n "${WAYLAND_DISPLAY:-}" ]; then
        return 0  # Already have Wayland
    fi
    if command -v xvfb-run &>/dev/null; then
        exec xvfb-run -a --server-args="-screen 0 1280x720x24" "$@"
    fi
    if command -v Xvfb &>/dev/null; then
        export DISPLAY=:99
        Xvfb :99 -screen 0 1280x720x24 &
        XVFB_PID=$!
        trap "kill $XVFB_PID 2>/dev/null" EXIT
        return 0
    fi
    echo "ERROR: No display server. Install: sudo apt install xvfb"
    exit 1
}

# === systemd service integration ===
if [ "${1:-}" = "--install-service" ]; then
    mkdir -p ~/.config/systemd/user/
    cat > ~/.config/systemd/user/phantom.service << EOF
[Unit]
Description=Phantom Antidetect Service
After=network.target

[Service]
Type=simple
ExecStart=${APP_DIR}/phantom-service.sh
Restart=on-failure
RestartSec=5
KillMode=control-group
Environment=DISPLAY=:99

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable phantom.service
    systemctl --user start phantom.service
    echo "Phantom service installed and started."
    exit 0
fi

# === Main ===
ensure_display "$0" "$@"
exec "${APP_DIR}/Phantom" --service "$@"
```

### Pattern E: Docker Image cho Headless Service

```dockerfile
FROM ubuntu:22.04

# System deps
RUN apt-get update && apt-get install -y \
    libwebkit2gtk-4.1-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    libxdo-dev \
    xdg-utils \
    xvfb \
    python3.12 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# App
COPY phantom /opt/phantom
RUN pip3 install -r /opt/phantom/requirements.txt

ENV DISPLAY=:99
EXPOSE 8765

ENTRYPOINT ["/usr/bin/xvfb-run", "-a", "--server-args=-screen 0 1280x720x24"]
CMD ["/opt/phantom/phantom-service", "--port", "8765"]
```

### Pattern F: Release Smoke Test Checklist (Human + CI)

```yaml
# .github/RELEASE_SMOKE_CHECKLIST.md

## Pre-release Checklist
### Automated (CI must pass)
- [ ] Lint: JS/TS, Rust (Clippy), Python (compileall)
- [ ] Security scan: CodeQL + OSV
- [ ] Unit tests: pytest + cargo test
- [ ] Build: Tauri + PyInstaller
- [ ] Backup: build on Windows + Linux

### CI Smoke Tests
- [ ] Windows: `--worker` mode fail fast test
- [ ] Windows: verify bundled packages
- [ ] Linux: `xvfb-run` headless service health check
- [ ] Portable ZIP extract + verify
- [ ] Installer.exe silent install + uninstall

### Manual (human verification)
- [ ] Clean Windows VM: install from scratch
- [ ] Clean Ubuntu VM: AppImage run + dpkg install
- [ ] Profile create/edit/delete
- [ ] Browser launch (Camoufox)
- [ ] Proxy configuration
- [ ] Update check (nếu có)
- [ ] Upgrade from previous version
- [ ] Export/import data
```

---

## Tóm tắt quyết định

| Vấn đề | Quyết định | Căn cứ |
|---|---|---|
| Framework | **Giữ Tauri 2.x** | Donut Browser ⭐3.4k chứng minh production-ready |
| Windows packaging fix | **Dùng pattern FoxDesk foxdesk.spec + taskkill/Job Objects** | FoxDesk v1.4.0 đã ship Windows thành công |
| Linux desktop | **AppImage + deb (Tauri built-in)** | Donut Browser pattern, Tauri action tự tạo |
| Linux headless service | **Docker + xvfb-run + systemd user service** | Tauri không native headless; xvfb-run là pattern chuẩn |
| Process cleanup | **Job Objects (Windows) + systemd scopes (Linux)** | `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` là cơ chế duy nhất reliable |
| CI/CD | **GitHub Actions matrix (win+linux)** | Cả Donut + FoxDesk đều dùng GHA |
| Smoke tests | **CI automated + manual pre-release checklist** | Kết hợp pattern FoxDesk + Donut |
| Volume control | **excludes list + không bundle browser binary** | FoxDesk đã fix từ 1.5 GB → 394 MB |
