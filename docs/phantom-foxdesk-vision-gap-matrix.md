# Ma Trận Gap: Phantom vs FoxDesk vs Vision

**Tác giả:** Hermes Agent  
**Ngày:** 2026-07-19  
**Mục đích:** So sánh kiến trúc Phantom hiện tại với FoxDesk (mã nguồn tham chiếu) và Vision (sản phẩm thương mại công khai). Đưa ra quyết định: **Keep** (giữ), **Replace** (thay bằng FOXDESK), **Add** (thêm mới).

---

## 1. Đóng gói (Packaging)

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Công cụ đóng gói** | `package-windows.py` thủ công → zip tay | PyInstaller + Inno Setup + GitHub Actions CI/CD | NSIS / tự động | **Replace → FoxDesk** | Phantom không có CI/CD, đóng gói thủ công không đáng tin cậy. FoxDesk có pipeline hoàn chỉnh. |
| **Windows installer** | Không có (chỉ zip) | `installer.iss` → FoxDesk-{version}-Setup.exe | Có | **Replace → FoxDesk** | Cần installer cho Windows deployment. |
| **Linux portable** | Không có | `foxdesk.spec` (PyInstaller), chưa có Linux build script | Có | **Add** | Phantom cần Linux headless, cần portable binary. |
| **macOS support** | Không | Không (chỉ Windows focus) | Có | **Defer** | Chưa phải ưu tiên. |
| **Frozen worker mode** | `python -m phantom.cli detached` | `--worker` flag trong frozen binary, dispatch engine theo runtime JSON | Có | **Replace → FoxDesk** | FoxDesk dispatch engine tự động trong cùng binary. |
| **Single-instance lock** | Không (nhiều instance có thể chạy) | Named mutex (Windows) + lock file (POSIX) | Có | **Replace → FoxDesk** | Tránh xung đột instance. |

---

## 2. Vòng đời tiến trình (Process Lifecycle)

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Start process** | `launch_blocking()` / `launch_detached()` | `start_process()` → ManagedProcess + ProcessRegistry | API REST | **Keep + Improve** | Cơ chế Popen cơ bản giống nhau, nhưng Phantom thiếu registry. |
| **Stop process** | `stop()` → SIGTERM → SIGKILL, walk /proc cho setsid'd grandchildren | `stop_popen()` → terminate → killpg → taskkill /T /F | API | **Keep** | Phantom có kỹ thuật giết process tree tốt (walk /proc). FoxDesk dùng `stop_popen`. Cần merge. |
| **Process registry** | Chỉ DB `running_instances` | `ProcessRegistry` với lock, tracking, monitor timeout/idle | Dashboard | **Replace → FoxDesk** | Phantom không có registry để monitor. FoxDesk có `ManagedProcess` đầy đủ. |
| **stdout capture** | Ghi vào file `launcher.log` (poll bằng GUI) | PIPE stdout → `_capture()` thread → logs array | API streaming | **Replace → FoxDesk** | FoxDesk capture real-time, parse JSON events. |
| **Idle auto-stop** | Không | `_monitor_timeouts()` kiểm tra idle minutes | Có | **Replace → FoxDesk** | Tiết kiệm tài nguyên. |
| **Process timeout** | Không | `ManagedProcess.timeout` → tự động kill | Có | **Replace → FoxDesk** | Phòng hờ process treo. |
| **Concurrency limit** | Không | `running_session_count()` → kiểm tra trước launch | Có | **Replace → FoxDesk** | Tránh quá tải. |

---

## 3. Local API

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Giao thức** | JSON-RPC over stdin/stdout (sidecar) | FastAPI REST trên 127.0.0.1:8765 | REST API | **Replace → FoxDesk** | Sidecar stdout là hạn chế lớn — chỉ 1 REQ mỗi lần gọi, không streaming, không WebSocket. FastAPI cho phép RESTful, SSE, WebSocket. |
| **Endpoint profile** | `sidecar.py` action-based | `GET /api/profiles`, `POST /api/profiles`, etc. | REST | **Replace → FoxDesk** | Chuẩn REST, dễ mở rộng. |
| **Endpoint session** | `launch/stop/status/log-tail` | `POST /api/sessions/launch`, `/stop`, batch stop, logs | REST | **Replace → FoxDesk** | FoxDesk có batch operations. |
| **Swagger/OpenAPI** | Không | FastAPI tự động sinh | Có | **Add** | Quan trọng cho dev và automation. |
| **Auth token** | Không | `X-FoxDesk-Token` random 32-byte, middleware bảo vệ /api/* | API Key | **Replace → FoxDesk** | Bảo vệ local API khỏi cross-process abuse. |
| **Streaming logs** | Poll `log-tail` mỗi 1s | Server-Sent Events hoặc WebSocket (cần thêm) | WebSocket | **Add** | Phantom poll model chậm; cần real-time. |
| **Runtime control** | Không (chỉ launch/stop) | `navigate`, `screenshot`, `evaluate`, `fingerprint_probe` qua command channel | CDP | **Replace → FoxDesk** | Phantom không thể điều khiển browser đang chạy. |

---

## 4. CDP / Playwright Attachability

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **CDP endpoint capture** | Không | `ws_endpoint` capture qua worker stdout, refresh button | CDP native | **Replace → FoxDesk** | Phantom không expose ws_endpoint → không thể attach từ ngoài. |
| **Server mode** | Không | `mode=server` → launch với `--server`, capture ws_endpoint | CDP always-on | **Replace → FoxDesk** | Cần cho agent automation (Playwright attach). |
| **Playwright attach** | Không | Lưu ws_endpoint → `playwright.connect()` | CDP | **Add + FoxDesk base** | Vision cho phép Puppeteer/Playwright attach. FoxDesk đã bắt ws_endpoint. |
| **Command channel** | Không | `.cmd.jsonl` / `.result.jsonl` file-based IPC | CDP direct | **Replace → FoxDesk** | File-based IPC cho phép navigate, evaluate, screenshot. |
| **Fingerprint probe (runtime)** | `probe_identity()` chỉ khi launch | Runtime probe qua command → fingerprint report | Built-in | **Replace → FoxDesk** | Phantom chỉ probe 1 lần khi start. |

---

## 5. Ephemeral Profiles

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **User data dir** | `platformdirs` / `PHANTOM_DATA_DIR`, profile roots tại `<data_dir>/profiles/profile_{id}` | Profile field `user_data_dir`, configurable | Auto-managed | **Keep** | Phantom 2.0 Task 2 đã bỏ path fixed trong project; persistent context giữ nguyên. |
| **Throwaway / ephemeral** | `persistent=False` trong verify | `persistent_context` toggle | Có | **Keep** | Phantom có khái niệm này, cần giữ và mở rộng. |
| **Temp profile on-the-fly** | Không | Tạo profile tạm không ghi vào store | Có | **Add** | Phoenix: launch browser tạm không cần tạo profile trước. |
| **Profile isolation** | user_data_dir riêng | user_data_dir riêng + engine isolation | Sandbox per profile | **Keep** | Cả 2 đều làm tốt. |
| **Profile templates** | Platform presets (facebook/tiktok/chatgpt) | `ProfileIn` + `templates_data.py` templates | Profile library | **Keep + Improve** | Phantom có preset tốt, FoxDesk có template UI. Cần merge. |

---

## 6. Observability

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Logs real-time** | Poll file `launcher.log` | `ProcessRegistry._capture()` → in-memory logs array | Web UI | **Replace → FoxDesk** | Phantom poll model chậm và không real-time. |
| **JSON event stream** | Không | Worker emit `{"event":"ready","ws_endpoint":"..."}` JSON events | Dashboard | **Replace → FoxDesk** | Phantom log text thô, không parse được structured data. |
| **Process status** | DB field `status` | `ManagedProcess.view()` → full status + pid + idle + errors | Dashboard | **Replace → FoxDesk** | FoxDesk trả về đầy đủ trạng thái. |
| **Health checks proxy** | Không | ProxyHealthScheduler + pool health status | Built-in | **Replace → FoxDesk** | Phantom không kiểm tra proxy health. |
| **Diagnostic export** | Không | System page → export diagnostic package (sanitized) | Có | **Replace → FoxDesk** | Debug support. |
| **Fingerprint consistency score** | Không | Static consistency check + runtime probe report | Built-in | **Replace → FoxDesk** | Phantom không có scoring. |
| **Error humanization** | Raw exception | `humanize_chromium_launch_error()` → actionable messages | Có | **Replace → FoxDesk** | UX critical cho người dùng. |

---

## 7. Concurrency

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Thread safety** | SQLite WAL mode + basic locks | `threading.RLock()` trên ProcessRegistry và ProfileStore | N/A | **Replace → FoxDesk** | FoxDesk lock toàn diện hơn. |
| **Multiple profiles** | Có, mỗi profile 1 process | Có, `ProcessRegistry` quản lý nhiều session | Có | **Keep** | Cả 2 đều hỗ trợ. |
| **Batch operations** | Không | `BatchLaunchRequest`, `BatchStopRequest` | Có | **Replace → FoxDesk** | Phantom chỉ launch/stop từng cái. |
| **Background worker** | CLI subprocess | Subprocess + stdout PIPE capture thread | Có | **Keep** | Tương tự. |
| **Async API** | Sync (CLI) | FastAPI async + sync workers | REST | **Replace → FoxDesk** | FastAPI async cho phép nhiều request đồng thời. |

---

## 8. Linux Headless

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Headless mode** | `headless='virtual'` (Xvfb), True, False | `headless: bool` trong `ProfileIn` | Có | **Keep + Improve** | Phantom có Xvfb tốt cho Linux. FoxDesk thiếu virtual mode. |
| **Xvfb support** | `headless='virtual'` → tự động Xvfb | Không (chỉ `headless=true/false`) | Có | **Keep + Add to FoxDesk** | Phantom Xvfb là lợi thế cho Linux server. Cần thêm vào FoxDesk. |
| **Display management** | Tự quản display | Không | Có | **Keep** | Phantom quản lý display tốt hơn. |
| **No display fallback** | Phát hiện DISPLAY, fallback Xvfb | Không | Có | **Keep** | Quan trọng cho server deployment. |
| **Chromium headless on Linux** | Không (Camoufox only) | Playwright/Patchright headless | Có | **Add** | Cần dual-engine. |

---

## 9. Bảo mật (Security)

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Proxy password storage** | Plain text trong DB | DPAPI (Windows) / local obfuscation (non-Windows) | Encrypted | **Replace → FoxDesk** | Phantom lộ proxy password. |
| **API auth** | Không | `X-FoxDesk-Token` random per process, constant-time compare | API Key | **Replace → FoxDesk** | Phantom không có auth → bất kỳ process local nào cũng có thể launch/stop. |
| **Data directory** | `platformdirs` + `PHANTOM_DATA_DIR` override | `%APPDATA%\FoxDesk` (Windows) / `~/.config/FoxDesk` (Linux) | Secure storage | **Done / retain** | Phantom 2.0 Task 2 đã chuyển DB/profiles/artifacts/runtime khỏi project directory; chưa có encrypted backup. |
| **Encrypted backup** | Không | `.fdk` file với password encryption, pre-restore snapshot | Cloud backup | **Replace → FoxDesk** | Phantom không có backup. |
| **Middleware token guard** | Không | `LocalApiTokenMiddleware` bảo vệ /api/* | Có | **Replace → FoxDesk** | Phantom sidecar stdin/stdout không cần auth. |
| **Single instance** | Không | Mutex + lock file | Có | **Replace → FoxDesk** | Tránh conflict. |
| **Token in UI** | Không | Token injection vào UI shell, không hardcode | SSO | **Replace → FoxDesk** | Phantom không có UI nên chưa cần. |

---

## 10. Tính năng khác

| Tiêu chí | Phantom (hiện tại) | FoxDesk (ref) | Vision (commercial) | Quyết định | Lý do |
|---|---|---|---|---|---|
| **Update manager** | Không | GitHub Release + ghproxy + SHA256 checksum + Token | Auto-update | **Replace → FoxDesk** | Phantom không thể tự cập nhật. |
| **Face/UI** | Tauri/React (không có code) | pywebview + WebView2 + native HTML/CSS/JS | Web UI | **Add (future)** | Phantom UI chưa viết xong. |
| **System tray** | Không | pystray với Show/StopAll/Quit | Có | **Replace → FoxDesk** | UX quan trọng cho desktop. |
| **Cookie management** | Chỉ persistent context | Import/export SQLite + Netscape, launch injection | Có | **Replace → FoxDesk** | Phantom không quản lý cookie được. |
| **Proxy pool** | Manual per profile | `ProxyPoolStore` + health scheduler + sticky/round_robin/random | Có | **Replace → FoxDesk** | Phantom không có pool. |
| **Tags / grouping** | Không | Profile tags + filter | Có | **Replace → FoxDesk** | Quản lý nhiều profile. |
| **Backup / restore** | Không | Password-encrypted `.fdk` + auto snapshot trước restore | Cloud | **Replace → FoxDesk** | Critical cho production. |
| **Dual-engine** | Camoufox only | Camoufox + Chromium (Playwright/Patchright/Auto) | Chromium | **Replace → FoxDesk** | Phantom chỉ có Firefox line. |

---

## Tổng hợp quyết định

| Hạng mục | Keep | Replace (FoxDesk) | Add (mới) |
|---|---|---|---|
| **Đóng gói** | 0 | 4 | 1 (Linux build) |
| **Vòng đời tiến trình** | 2 (stop, concurrency) | 3 | 0 |
| **Local API** | 0 | 5 | 2 (OpenAPI, streaming) |
| **CDP/Playwright attach** | 0 | 3 | 1 (Playwright.connect) |
| **Ephemeral profiles** | 3 | 0 | 1 (temp profile) |
| **Observability** | 0 | 5 | 0 |
| **Concurrency** | 2 | 3 | 0 |
| **Linux headless** | 3 | 1 | 1 (Chromium headless) |
| **Bảo mật** | 0 | 6 | 0 |
| **Tính năng khác** | 0 | 7 | 1 (Tauri UI) |
| **Tổng** | **10** | **37** | **7** |

### Chiến lược chuyển đổi

1. **P0 — Ngay lập tức:**
   - Adopt `backend/app.py` (FastAPI) làm local API server → thay thế sidecar JSON-RPC
   - Adopt `ProcessRegistry` + `ManagedProcess` + `start_process()` → quản lý lifecycle chuyên nghiệp
   - Adopt `worker_command` / `.cmd.jsonl` / `.result.jsonl` → runtime control channel
   - Adopt `X-FoxDesk-Token` middleware → bảo vệ local API
   - Adopt `ProxyPoolStore` + `ProxyHealthScheduler` → quản lý proxy

2. **P1 — Quan trọng:**
   - Adopt `camoufox_worker.py` + `chromium_worker.py` → dual-engine
   - Adopt `session_control.py` → navigate, evaluate, screenshot
   - Adopt `setup_manager.py` + `update_manager.py` → cập nhật tự động
   - Adopt `backup_crypto.py` → backup mã hóa
   - Add Linux build script (PyInstaller)
   - Add Playwright CDP attach từ ws_endpoint

3. **P2 — Cải thiện:**
   - Giữ lại Xvfb (`headless='virtual'`) từ Phantom
   - Giữ lại process tree kill (`_descendants()`) từ Phantom
   - Giữ lại profile presets (platform tags) từ Phantom
   - Giữ lại persistent identity (6 blobs) từ Phantom
   - Add temp profile launch (không cần tạo profile trước)
   - Add OpenAPI/Swagger docs
   - Add Server-Sent Events cho log streaming

### Những gì Phantom giữ lại (Keep = 10)

| STT | Tính năng | Lý do |
|---|---|---|
| 1 | `headless='virtual'` (Xvfb) | FoxDesk không có virtual mode; Phantom làm tốt cho Linux |
| 2 | `_descendants()` walk /proc | FoxDesk dùng `stop_popen` đơn giản hơn; Phantom bắt được setsid'd grandchildren |
| 3 | `_kill_tree_windows()` taskkill /T /F | Cả 2 đều có, giữ logic Phantom |
| 4 | `launch_detached()` | Cơ chế subprocess cơ bản giống nhau |
| 5 | Persistent identity 6 blobs | Phantom làm rất tốt fingerprint determinism với seeds, webgl, fonts, voices |
| 6 | Platform presets | Phantom có facebook/tiktok/chatgpt presets tốt hơn FoxDesk |
| 7 | `persistent=False` cho throwaway | Profile tạm cho verify |
| 8 | User data dir isolation | Cả 2 đều làm, giữ nguyên |
| 9 | Thread safety SQLite | Phantom WAL mode ổn |
| 10 | Concurrency multiple profiles | Mỗi profile 1 process |

### Những gì thay bằng FoxDesk (Replace = 37)

FoxDesk cung cấp ~37 tính năng Phantom thiếu hoặc làm kém hơn, bao gồm:
- Toàn bộ local API (FastAPI REST + token auth)
- Process lifecycle chuyên nghiệp (registry, monitor, idle timeout)
- Dual-engine (Firefox + Chromium/Playwright/Patchright)
- Runtime control channel (navigate, evaluate, screenshot)
- CDP ws_endpoint capture
- Proxy pool + health checks
- Cookie import/export
- Encrypted backup/restore
- Update manager + SHA256
- Diagnostics export
- PyInstaller + Inno Setup packaging + CI/CD
- Batch operations
- Templates + tags

### Những gì thêm mới (Add = 7)

1. **Linux portable build** — PyInstaller cho Linux (hiện FoxDesk chỉ build Windows)
2. **OpenAPI/Swagger** — FastAPI auto, cần expose
3. **Log streaming SSE** — Server-Sent Events cho real-time log
4. **Playwright CDP attach** — `playwright.connect(ws_endpoint)` cho agent automation
5. **Temp profile on-the-fly** — Launch browser không cần tạo profile DB trước
6. **Chromium headless Linux** — Thêm headless Chromium support cho Linux
7. **Tauri UI** (tương lai) — Phantom đã có Tauri scaffold, cần hoàn thiện

---

## Sơ đồ kiến trúc đích (Phantom 2.0)

```
┌─────────────────────────────────────────────────────┐
│                   Phantom Desktop                    │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Tauri GUI   │  │ System Tray │  │ CLI (sidecar)│ │
│  │ (React)     │  │ (pystray)   │  │ (fallback)   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘ │
│         │                │                │         │
│         └────────────────┼────────────────┘         │
│                          │ X-FoxDesk-Token           │
│                    ┌─────▼─────┐                    │
│                    │ FastAPI    │ ← Port from FoxDesk│
│                    │ 127.0.0.1 │                    │
│                    └─────┬─────┘                    │
│                          │                          │
│  ┌───────────────────────┼───────────────────────┐  │
│  │      ProcessRegistry    │   ProfileStore       │  │
│  │    (FoxDesk port)      │  (FoxDesk port)      │  │
│  ├────────────────────────┼───────────────────────┤  │
│  │  Worker: camoufox      │  Worker: chromium     │  │
│  │  .cmd.jsonl/.result    │  .cmd.jsonl/.result   │  │
│  │  ws_endpoint capture   │  CDP attach           │  │
│  └────────────────────────┴───────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  ProxyPoolStore + ProxyHealthScheduler       │   │
│  │  BackupCrypto + UpdateManager + SetupManager │   │
│  │  SettingsStore + Templates                   │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Phantom Keep:  Xvfb, descendants() tree     │   │
│  │  identity 6-blobs, platform presets          │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```
