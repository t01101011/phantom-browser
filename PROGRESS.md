# Phantom Browser — Progress

> **Snapshot 20/07/2026 (Phantom 2.0 execution)** · Tasks 1–12, 14–16 DONE trên Linux; Task 13 IMPLEMENTED/PENDING WINDOWS CI · Task 16 controlled stock-Chromium Linux coherence gate PASS có unsupported rõ ràng cho WebGPU/TLS/HTTP2; không có Windows/TLS evidence giả · full Python suite PASS (xem log cuối) + 5/5 frontend + 3/3 Rust · Task 14 authenticated Docker/Linux smoke PASS, clean shutdown/no orphan · Task 15 stock/Clearcote/fingerprint-chromium Linux probes + ADR complete
> Đọc file này trước khi pick up lại. Mọi context đều ở đây.

---

## INDEX (jump-to)

- [Project meta](#project-meta)
- [Dev env setup](#dev-env-setup)
- [Phase 0 status](#phase-0-status)
- [Phase 1 status](#phase-1-status)
- [Phase 2 status](#phase-2-status) ← NEW session 5
- [Session log](#session-log)
- [Closed bugs (session 2)](#closed-bugs)
- [Open bugs (cho session sau)](#open-bugs)
- [Next steps](#next-steps)
- [Skill/lessons learned](#skilllessons-learned)

---

## Project meta

| K | V |
|---|---|
| Path | `/root/projects/phantom-browser/` |
| Plan | `.hermes/plans/2026-07-19_132233-phantom-browser-2-agent-first.md` (authoritative) · `plan.md` (living summary) |
| Ghim Discord | `#phantom-browser` (PERSONAL) |
| Notion project | `399539c8-7ba9-811c-9b07-d0f19fb583ce` |
| Target build | Windows-first, core cross-platform; Linux VPS agent runtime là first-class |
| Sàn ưu tiên | FB/TikTok + ChatGPT |
| Proxy | 2 residential đã có (Mobite Network LLC, exit Kalispell US) |
| Secrets | `.env` (PROXY_1_*, PROXY_2_*) — KHÔNG commit |

---

## Dev env setup

```bash
cd /root/projects/phantom-browser
.venv/bin/python    # Python 3.11.15 venv riêng
```

Packages installed:
- camoufox 0.5.4 (+ extras: geoip → maxminddb, geoip2)
- browserforge 1.2.4
- playwright 1.60.0
- platformdirs 3+; pytest 9 (dev)
- pillow, pytesseract, requests (dev utilities)
- tesseract-ocr (apt) — để OCR screenshot CreepJS

Browser binary: `~/.cache/camoufox/browsers/official/152.0.4-beta.28-924f3109/` (1.2GB)
GeoIP DB: MaxMind GeoLite2 (download tự động khi `geoip=True`)

**Rust + Tauri toolchain (session 5):**
- Rust 1.97.1 (`rustup minimal`, `~/.cargo/bin`)
- WebKitGTK 4.1 + libsoup-3.0 + javascriptcoregtk-4.1 + librsvg2-dev + libgtk-3-dev + pkg-config + libayatana-appindicator3-dev (apt)
- `@tauri-apps/cli` 2.11.4 + `@tauri-apps/api` 2.11.1 (qua `npm install` trong `tauri-app/` — NOT `cargo install tauri-cli`, npm prebuilt vs cargo source compile ~10min)
- Xvfb display `:99` cho headless webview testing (`Xvfb :99 -screen 0 1280x800x24`)
- Build binary tại `tauri-app/src-tauri/target/debug/tauri-app` (263MB debug)

---

## Phase 0 status

Spike scripts: `spike/spike_0{1,2,3,4,5,6,7}_*.py`. Output: `spike/out/`, logs: `spike/spike*.log`

**Phase 0 ✅ DONE** → Phase 1 backend MVP implemented (see `src/phantom/`).

| Spike | Mục đích | Kết quả | File |
|---|---|---|---|
| 01 | Camoufox launch + fingerprint serialize-roundtrip + determinism | ✅ identical 2 runs | `spike_01_basic_launch.py` |
| 02 | Launch với proxy + cross-proxy fingerprint stable | ✅ exit IP đúng, UA/screen stable | `spike_02_proxy_fingerprint.py` |
| 03 | Test trên creepjs/browserleaks thật | ✅ "0% headless", UA stable | `spike_03_test_sites.py` |
| 04 | Stable canvas/audio/font seeds qua `config=` | ❌ Canvas sig vẫn đổi | `spike_04_stable_seeds.py` |
| 05 | Dump `launch_options` config 2 lần, diff field random | ✅ Tìm root cause: webGl vendor/renderer + window.history.length random | `spike_05_dump_config_diff.py` |
| 06 | Fix BUG-1/2/3/4: lock webgl/fonts/voices/screenY/locale + ff_version=152 + TZ override + Xvfb | ✅ Config 49/49 keys stable, WebGL enabled; canvas cross-process vẫn drift (Linux headless font rasterizer) | `spike_06_fix_canvas_stable.py` |
| 07 | Full CAMOU_CONFIG diff 2 launches | ✅ 0 drift (sau fix spike_06) | `spike_07_full_config_diff.py` |

**Verified working (session 2):**
- Camoufox engine chạy không bị CreepJS flag là headless
- BrowserForge fingerprint serialize → JSON → reconstruct → reuse OK
- Proxy auth `user:pass` work, exit IP đúng proxy IP
- Cross-proxy: UA/platform/oscpu/screen/outer/inner/screenXY/histLen/DPR stable byte-for-byte
- WebGL vendor/renderer lock qua `sample_webgl('win', vendor, renderer)` lookup → stable
- `from_browserforge(fp, ff_version='152')` → UA đúng `rv:152.0` (fix BUG-2)
- TZ override `America/Denver` trong config → win GeoIP setdefault (fix BUG-4)
- Locale pin `en-US` → kill GeoIP random language (thêm mới)
- `headless='virtual'` (Xvfb) → WebGL enabled, vendor/renderer đúng locked values
- **Canvas same-page (3 lần vẽ trong 1 page) → STABLE** — browser trong 1 process deterministic

---

## Phase 1 status

Backend MVP in `src/phantom/` — installable, runnable, tested end-to-end.

| File | Role |
|---|---|
| `src/phantom/schema.sql` | profiles + running_instances tables, indexes |
| `src/phantom/db.py` | sqlite3 stdlib CRUD + WAL + proxy dup-count helper |
| `src/phantom/identity.py` | `generate_identity()` → 6 persistent blobs; `build_launch_config()` → full deterministic config (port from spike_06) |
| `src/phantom/presets.py` | facebook / tiktok / chatgpt / custom presets |
| `src/phantom/launcher.py` | `launch_blocking()` + `stop()` (SIGTERM/SIGKILL) + `probe_identity()` |
| `src/phantom/cli.py` + `__main__.py` | argparse CLI: init/create/list/show/launch/verify/stop/delete |
| `pyproject.toml` | `pip install -e .` so `python -m phantom.cli …` works |

**Verified (session 3; storage path updated by Phantom 2.0 Task 2):**
- `python -m phantom.cli init` → DB created at platform data dir (`platformdirs`), hoặc `$PHANTOM_DATA_DIR/phantom.db` khi override
- `create` → 6 blobs generated + persisted; duplicate-proxy warning fires when same proxy already used
- `list` / `show` print tables + profile detail (webgl vendor visible)
- `verify` → launches headless virtual (Xvfb), probes ip-api + navigator + WebGL, exits cleanly, DB status flips back to `idle`
- **Determinism check: 2 launches of profile-1 → 16/16 keys byte-identical** (userAgent, timezone, language, platform, oscpu, screenW/H, outer/inner W/H, screenY, histLen, DPR, webglVendor, webglRenderer) + exit IP stable (`23.133.196.201`)
- `stop` correctly reports "not running" when nothing running; `delete` removes row

**Remaining for Phase 1 → Phase 2 handoff:** ✅ BOTH SOLVED (session 4)

- ✅ **`launch_detached` (subprocess)** — implemented + tested. `launcher.launch_detached()` spawns `python -m phantom.cli detached <id>` in its own session (`start_new_session=True`); parent returns immediately với child pid, child ghi vào `<data_dir>/profiles/profile_<id>/launcher.log`.
- ✅ **`stop()` process-group kill** — `stop()` now walks `/proc` for setsid'd descendants (Xvfb, playwright node) and SIGKILLs them explicitly. Returns only when the recorded pid is gone from `/proc` (not just a zombie). Verified: child + Firefox + Xvfb all dead, DB cleared, no orphans.
- ✅ **Cookie/session persistence** — `launch_blocking(persistent=True)` (default) passes `user_data_dir` + `persistent_context=True` to `Camoufox()`. Routes through `playwright.firefox.launch_persistent_context`. Verified: marker cookie set in launch 1 survives into launch 2 across same profile dir.
- ✅ **No determinism regression** — `verify_profile_determinism.py` re-run on persistent-context path: 16/16 keys + exit IP byte-identical across 2 launches.

**Phase 2 blockers cleared. Ready for Tauri GUI shell.**

---

## Phase 2 status

**GUI shell scaffolded + e2e sidecar flow PASSED (session 5, 2026-07-19) → Windows hand-off ready (session 6, 2026-07-19).**

| File | Role |
|---|---|
| `src/phantom/sidecar.py` | JSON-RPC over stdio — 9 actions (list/get/create/launch/stop/delete/status/log-tail/presets). Envelope `{ok, data}` / `{ok:false, error:{code,message,detail}}`. Exit 0 even on logical error so Rust can always parse stdout. |
| `docs/sidecar-contract.md` | Stable contract spec between Rust shell + Python sidecar (ProfilePublic schema, error codes, polling pattern) |
| `tauri-app/src-tauri/src/lib.rs` | Rust bridge: `sidecar_call(action, args)` Tauri command → `repo_root()` resolve (env override / dev / ship beside exe) → `sidecar_command(root)` returns platform-specific python path (Linux `.venv/bin/python`, Windows `.venv/Scripts/python.exe`) → load `.env` → spawn `python -m phantom.sidecar` → parse envelope → return `serde_json::Value`. No PyInstaller — see `scripts/windows-setup.ps1`. |
| `tauri-app/src-tauri/Cargo.toml` | Tauri 2 + `tauri-plugin-shell` + `tauri-plugin-opener` + serde/serde_json |
| `tauri-app/src-tauri/tauri.conf.json` | Title "Phantom Browser", window 1280×800, minSize 900×600, identifier `com.tk.phantombrowser` |
| `tauri-app/src-tauri/capabilities/default.json` | `shell:allow-execute`, `shell:allow-spawn`, `core:default`, `opener:default` |
| `tauri-app/src/App.tsx` | Profile table + Create form + Log drawer (1.5s poll) + Toast. Dark goth theme. |
| `tauri-app/src/sidecar.ts` + `src/api.ts` | TS types for envelope + per-action wrappers (typed) |
| `tauri-app/src/App.css` | Dark theme, status pills (running=amber pulse), platform tags (FB blue / TikTok pink / ChatGPT green / custom gray) |
| `tauri-app/package.json` | React 19 + Vite 7 + `@tauri-apps/cli` 2.11.4 + `@tauri-apps/api` 2 |
| `dist/windows/phantom-browser.exe` | **(NEW session 6)** Cross-compiled Windows release binary, 23MB PE32+ GUI x86-64. Built via `cargo build --release --target x86_64-pc-windows-gnu` on Linux with mingw-w64. Created by copying `target/x86_64-pc-windows-gnu/release/tauri-app.exe` (Cargo crate name is `tauri-app`, but product name (`tauri.conf.json`) is "Phantom Browser"; mainBinaryName is Tauri 3 only). |
| `scripts/windows-setup.ps1` | **(NEW session 6)** PowerShell setup script for tk's Windows machine. Creates `.venv`, `pip install -e .`, `camoufox sync + fetch`, smoke-tests sidecar. Replaces PyInstaller (can't cross-build from Linux). Re-run after `git pull` to refresh deps. |
| `.env.example` | **(NEW session 6)** PROXY_1_* / PROXY_2_* template. User copies to `.env`, fills real creds. |
| `src/phantom/launcher.py` (stop Windows port) | **(NEW session 6)** `IS_WINDOWS` module constant + `_stop_windows(profile_id, pid)` branch in `stop()`. Uses `taskkill /T /F /PID` (kills whole tree, replaces Linux's `_descendants()` + `killpg`) + `OpenProcess`/`GetExitCodeProcess` checking `STILL_ACTIVE=259` (replaces `/proc/<pid>` existence). Linux path unchanged + verified no-orphan regression. |

**Verified (session 5):**
- `cargo check` clean, `tsc --noEmit` clean, `vite build` clean (200KB JS)
- `tauri build --no-bundle --debug` → binary 263MB at `src-tauri/target/debug/tauri-app`, ELF executable
- App launches alive under Xvfb :99 (`DISPLAY=:99 GDK_BACKEND=x11`), no crash in 5s
- **e2e sidecar flow PASSED**: launch (pid 163354) → status flips running → log-tail reads `[phantom profile 1 running]` live → stop → DB idle → orphan check clean (only Xvfb :99 server remains, correct)
- Sidecar alone tests clean: `list` / `presets` / `status` / `get not_found` / `create bad_proxy` all return well-formed JSON envelopes

**Why a separate `sidecar.py` instead of `cli.py --json`**: `cli.py` is tk's human CLI (text tables, `[+]` prefixes, `sys.exit()` on errors). Retrofitting `--json` risks breaking the terminal UX. `sidecar.py` is JSON-only from ground up: never prints non-JSON, never non-zero exit except on stdlib crash. One file = easy to swap with PyInstaller standalone for ship.

**Phase 2 remaining (not blockers, just ship/prep):**
- `npm run tauri dev` under Xvfb + click launch from UI in real webview (currently verified app boots + sidecar alone; interactive click not yet exercised) — needs tk's machine
- Windows cross-compile (`x86_64-pc-windows-gnu` + mingw-w64) — binary for tk's machine ✅ DONE session 6
- PyInstaller bundle `phantom-sidecar.exe` to ship alongside Windows binary — ❌ UNFEASIBLE (PyInstaller không cross-compile Linux→Win). Replaced by `scripts/windows-setup.ps1` ✅ DONE session 6
- `stop()` Windows port: replace `/proc` walk + `os.killpg` with `taskkill /T /PID <pid>` or ctypes `OpenProcess`/`TerminateProcess` tree walk (no `/proc` on Win, `killpg` only POSIX) ✅ DONE session 6 (Linux path also re-verified, no orphans)

**Session 6 remaining:** hand the `dist/windows/phantom-browser.exe` + `scripts/windows-setup.ps1` to tk to: run setup on his Windows machine, fill `.env`, launch `phantom-browser.exe`, launch a profile FROM the GUI, login FB/TikTok for real. That final human test is the only thing left.

---

## Audit + Task 8 — 20/07/2026

- **Tasks 1–7 DONE trên Linux.** Task 6 có adapter đủ 9 operation, parser reject malformed/out-of-order, legacy launcher wrapper và 6-blob identity tests. Negative worker subprocess smoke trước audit trả đúng một event `seq=1`, `PROFILE_NOT_FOUND`, exit 1. Không chạy lại production Camoufox determinism vì wrapper `scripts/verify_profile_determinism.py` vẫn không tồn tại và live launch bị giới hạn; bằng chứng production hai lần byte-identical ở audit trước được giữ nguyên, không nâng thành kết quả mới.
- Task 7: focused runtime **46 pass**, crash smoke trước audit PASS/no orphan; Linux process-group + `/proc` cleanup verified. Windows Job Object/taskkill logic chỉ có fake/platform-neutral tests tại đây; native Windows smoke vẫn pending.
- Task 8 thêm migration v3, `SessionService`, REST start/list/get/delete, durable events/SSE resume, state machine, start/stop idempotency, action capabilities (không giả CDP), max concurrency + FIFO, startup reconciliation.
- Verification cuối: `pytest -q` → **192 passed**; Vite/TypeScript build PASS; Rust `cargo test -q` PASS. Live uvicorn HTTP smoke PASS (auth, create profile, idempotent start, stop, SSE replay). Worker thật trong smoke bị stop trước ready nên final `stopped` sau fix; browser/Camoufox headed determinism không được claim bởi Task 8 smoke.
- Files Task 8: `src/phantom/migrations/0003_persistent_sessions.sql`, `src/phantom/services/session_service.py`, `src/phantom/api/routes_sessions.py`, `src/phantom/api/routes_events.py`, `tests/api/test_sessions.py`, `tests/api/test_events.py`; sửa `app.py`, migration tests và docs.

---

## Session log

### 2026-07-20 — Task 16: Stealth coherence gate + release acceptance ✅ DONE LINUX

- Thêm normalized schema/evaluator deterministic và CLI artifact có SHA-256/redaction. Required main, DedicatedWorker, SharedWorker, ServiceWorker là hard gate; missing/unsupported worker luôn FAIL. Optional UA-CH/WebGPU/TLS/HTTP2 giữ `unsupported`, không đổi thành PASS; `--require-complete` có thể nâng thành release hard-fail.
- TDD fixtures: good `conditional_pass`; bad drift UA-CH/SharedWorker/locale/relaunch trả exit 1. Focused 12 PASS; full Python **225 passed in 6.79s**.
- Real controlled localhost stock Playwright Chromium Linux chạy persistent profile hai relaunch: **21 pass, 0 fail, 6 unsupported**; raw/verdict + `SHA256SUMS` ở `task16-artifacts/`; no Task16 browser orphan.
- Linux/Windows release workflows chạy probe + gate và upload raw evidence. Windows workflow chưa chạy tại đây: **Task 13 giữ IMPLEMENTED/PENDING WINDOWS CI**, không claim native Windows. TLS ClientHello/HTTP2 và WebGPU adapter attestation chưa captured; blockers được giữ rõ trong `docs/stealth-coherence.md`.

### 2026-07-20 — Task 12: React GUI dùng HTTP control plane ✅

- Thay direct `sidecar_call` bằng typed REST/SSE client dùng đúng API của agents. GUI có folder sidebar/filter, search profile, create/edit/clone/delete, proxy create/health/delete, start/stop, status/capabilities và SSE event drawer; không giả `cdp_url`.
- Security: bearer token chỉ lấy qua `control_plane_config` IPC và module memory; không local/sessionStorage, query URL hay logs. CORS allowlist loopback Vite + `tauri://localhost`, không cookie credentials.
- Rust bootstrap chạy một Python control plane trên loopback, đọc token path qua production module, đợi authenticated `/readyz`, giữ child handle và kill/wait khi app drop. Dev hỗ trợ `PHANTOM_REPO`/`PHANTOM_PYTHON`; standalone Python packaging thuộc Task 13 nên chưa claim production release.
- Audit bắt 3 bug thật và fix có regression tests: `Camoufox` phải gọi context-manager `__enter__/__exit__`; profile direct không được truyền proxy URL rỗng/GeoIP; SSE parser xử lý CRLF, malformed event, cancel và reconnect `Last-Event-ID`.
- Evidence cuối: `pytest -q` **210 passed**; Vitest **5 passed**; Cargo **3 passed**; TSC/Vite build PASS; `tauri build --no-bundle --debug` PASS. Live FastAPI + real Camoufox dưới Xvfb: profile create/list, session đạt `ready`, capabilities action-only/no CDP, stop request `stopping`, process cleanup không orphan. Tauri debug binary boot và child shutdown verified.
- Boundary: browser automation ngoài Tauri chỉ inspect được Vite shell (Tauri IPC không tồn tại trong Chrome), nên không claim automated native WebView click-through hoặc Windows. Task 13 chưa làm trong phiên này vì acceptance bắt buộc native `windows-latest`; không tạo pipeline chưa thể exercise.

### 2026-07-20 — Task 10: Agent actions và token-efficient snapshots ✅

- Thêm lease-guarded action endpoint cho `navigate/snapshot/click/type/press/scroll/select/screenshot`; lỗi structured gồm `STALE_REF`, `REF_NOT_FOUND`, `LEASE_MISMATCH`, `SESSION_NOT_READY`.
- Snapshot chỉ trả interactive visible elements với stable `eN` refs theo generation, role/name/value; không trả full DOM. Watchdogs phát popup/download/crash events.
- Humanized input v1 chạy controller-side, timing seeded/deterministic; không claim tương đương custom-engine CDP của Vision.
- Verification: RED import failure trước implementation; focused **6 passed**, full Python **202 passed**. Headed Chromium qua Xvfb smoke PASS: snapshot/type/click/stale-ref/screenshot (7,579 bytes). Native Camoufox/Windows chưa được claim.
- Next: Task 11 — MCP Streamable HTTP adapter.

### 2026-07-20 — Task 11: MCP Streamable HTTP adapter ✅

- Mount canonical `/mcp` trong FastAPI, dùng official MCP Python SDK stateful Streamable HTTP; lifecycle session manager nằm trong lifespan chung, không có stdio daemon thứ hai.
- Bearer auth dùng cùng token/constant-time comparison với REST. 10 tools: list/create profile, start/stop/acquire lease, navigate/snapshot/click/type/screenshot; gọi trực tiếp cùng service instances và trả compact structured content/errors. Không tạo hoặc quảng cáo CDP URL.
- Protocol validation bao gồm missing/wrong auth, initialize, tools/list, tools/call, schema/unknown-tool errors, domain error mapping, malformed JSON, Accept negotiation và DELETE session lifecycle.
- Evidence: focused `4 passed`; full `206 passed in 6.56s`. Live uvicorn smoke: unauth 403, initialize 200 (`2025-03-26`, session id), 10 tools, create-profile PASS, `SESSION_NOT_FOUND` structured `isError`, DELETE 200.
- Chưa chạy TS/Vite/Rust vì Task 11 không chạm frontend/Rust. Không claim Windows/native Camoufox.
- Next: Task 12 — chuyển React GUI sang HTTP control plane.

### 2026-07-20 — Task 9: instant sessions, leases, TTL và artifacts ✅

- Instant sessions dùng isolated temp user-data dir, chung max-concurrency/FIFO và idempotency của control plane; stop/crash/reconcile đều cleanup temp dir.
- Lease token chỉ trả một lần và DB chỉ giữ SHA-256; generation/owner guard, heartbeat không lùi expiry, TTL reaper dừng session và ghi durable events.
- Artifact screenshot/cookies/storage có allowlist MIME/type, size/retention limits, SHA-256 metadata, path containment/traversal defense và redaction credential fields trong JSON.
- Verification: focused **4 passed**, full Python **196 passed**. Live uvicorn smoke với no-process adapter: instant HTTP 201, artifact secret redacted, TTL final `stopped`, temp dir deleted. Không claim browser Camoufox/Windows native.
- Next: Task 10 — indexed accessibility snapshots và actions.

### 2026-07-19 — Task 5: Profile/folder/proxy REST CRUD ✅

**Task 5 mục tiêu:** Port profile/folder/proxy CRUD sang REST v1 — GUI, CLI và agent cùng một contract.

**Đã làm:**
1. **Service layer** (`src/phantom/services/profile_service.py`, `proxy_service.py`):
   - Transaction-safe CRUD với optional `conn` kwarg cho caller share transaction.
   - `_public_profile()` / `_public_proxy()` strip `proxy_pass`, fingerprint blobs và password.
   - Clone profile giữ nguyên proxy/timezone/locale, tạo fresh identity (6-blob).
   - Bulk import preview (validate không write) + apply (single transaction).
   - Proxy health check qua `urllib` → `httpbin.org/ip`, ghi `health_status` DB, không log credential.

2. **REST endpoints** (`src/phantom/api/routes_profiles.py`, `routes_folders.py`, `routes_proxies.py`):
   - `/v1/profiles` — full CRUD + clone + clone-name uniqueness + import/preview + import.
   - `/v1/folders` — full CRUD + parent_id validation + name uniqueness + cascade protection (refuse delete if profiles reference folder).
   - `/v1/proxies` — full CRUD + duplicate name/port validation + cascade protection + `POST /{id}/check` health endpoint.
   - Tất cả endpoint yêu cầu Bearer token auth (403 nếu thiếu/sai).
   - Pydantic models (`models.py`) validate input, response models strip secrets.

3. **API tests** (`tests/api/test_profiles.py`, `test_folders_proxies.py`):
   - Profile CRUD: create, duplicate name, missing required, list, filter, get, update, delete, not-found.
   - Clone: success, not-found (conflict).
   - Bulk import: preview (valid/error counts), apply (created).
   - Auth: 8 profile endpoints, 5 folder endpoints, 6 proxy endpoints — all require token.
   - Folder CRUD: create, duplicate, parent, invalid parent, list, get, update, delete, not-found.
   - Proxy CRUD: create (password redacted `*****`), duplicate, invalid port, list, get, update, delete, not-found.
   - Proxy health: not-found returns 404 (full health check needs external connectivity).

**Files mới:**
- `src/phantom/api/routes_profiles.py` — profile CRUD REST routes
- `src/phantom/api/routes_folders.py` — folder CRUD REST routes
- `src/phantom/api/routes_proxies.py` — proxy CRUD REST routes
- `src/phantom/services/profile_service.py` — profile business logic
- `src/phantom/services/proxy_service.py` — proxy business logic + health check
- `src/phantom/services/__init__.py` — package init
- `tests/api/test_profiles.py` — profile API tests
- `tests/api/test_folders_proxies.py` — folder + proxy API tests
- `scripts/smoke_test_task5.py` — live REST smoke test script

**Files sửa:**
- `src/phantom/api/app.py` — mount profiles/folders/proxies routers
- `src/phantom/api/models.py` — thêm ProfileCreate/Update/Response/CloneRequest, Folder CRUD models, Proxy CRUD/Health models

**Verification:**
- `pytest -q` → **119 passed, 1 warning in 2.63s** (up from 65 tests in Task 4)
- **Live REST smoke test** (32 checks) — auth, profile CRUD + clone + import preview/apply, folder CRUD + parent + cascade, proxy CRUD + password redaction + health check + delete cascade — **32/32 PASS**
- Secret redaction verified: `proxy_pass` và `fingerprint_json` absent từ profile response, proxy `password` = `*****`

**Decisions locked (Task 5):**
- **Service layer với optional `conn`** — cho phép caller share transaction (bulk import, future composite operations) mà không bắt route phải biết DB internals.
- **`_public_profile()` strip cả `proxy_pass` + 6 fingerprint blobs** — API response chỉ chứa metadata, không leak identity seed. Sidecar cũ strip (legacy), giờ API đồng bộ.
- **Proxy health check dùng `urllib` không phải `requests`** — tránh thêm dependency. `httpbin.org/ip` parse JSON, trả exit_ip + latency_ms. Không log credential.
- **Folder/Proxy cascade: 409 thay vì cascade delete** — an toàn hơn, không mất data nếu user chưa kịp re-assign.

---

### 2026-07-19 — Phantom 2.0 execution: Tasks 1–3 complete

**Task 1 — characterization safety net:**
- Thêm tests cho DB CRUD/WAL/FK/running cleanup, 6-blob identity determinism, đủ 9 sidecar actions/envelopes/redaction và launcher detached/state.
- TDD bắt bug Windows thật: `_pid_alive()` bị định nghĩa hai lần; implementation Linux-only ở cuối file đè mất runtime Windows dispatch. Đã xóa duplicate.
- Production `phantom.cli verify fb-test-1` chạy hai lần cho cùng exit IP và navigator/screen/WebGL byte-identical.

**Task 2 — paths/settings/secrets:**
- Thêm `src/phantom/paths.py`: `platformdirs` default + `PHANTOM_DATA_DIR` override; layout `phantom.db`, `profiles/`, `artifacts/`, `runtime/`.
- Migrate DB, launcher và sidecar khỏi runtime paths trong project directory. Không tự move DB/profile cũ trong task này.
- Thêm `src/phantom/settings.py` với recursive redaction cho proxy credentials, token/API key và public payload.
- Parent verification bắt lỗi first-run `sqlite3.OperationalError: unable to open database file`; fix bằng cách mkdir parent trước `sqlite3.connect()`.
- Verification cuối: **43/43 tests PASS**; CLI default data dir và override smoke đều PASS.

**Task 3 — schema v2 + migrations:**
- Thêm `schema_migrations` ledger và transaction-safe migration runner trong `src/phantom/migrations.py`.
- Migration additive `0002_control_plane.sql` thêm folders, proxies, sessions, leases, events, artifacts; profiles v1 chỉ thêm nullable foreign keys nên legacy sidecar vẫn đọc được.
- Thêm indexes cho profile/status, lease expiry và event/artifact creation time; bundle SQL assets vào wheel qua setuptools package-data.
- Verification cuối: **49/49 tests PASS**; empty/v1/idempotent/backup-restore tests PASS, SQLite FK/integrity sạch, CLI init + sidecar list smoke PASS.

**Current next step:** Task 9 — instant sessions, leases, TTL và artifacts. Tasks 1–8 đã xanh trên Linux; Windows Job Object/native browser smoke vẫn cần CI hoặc máy Windows thật.

---

### 2026-07-19 — Task 4: FastAPI control plane tối thiểu ✅

**Task 4 mục tiêu:** Thay command-per-process bằng server local lâu dài mà chưa bỏ sidecar.

**Đã làm:**
1. **Fix 3 test failures** của partial Task 4:
   - `test_token_auto_generated_and_persisted` + `test_token_file_permissions`: move `load_or_generate_token()` từ `lifespan` handler lên `create_app()` (eager evaluation) để token được tạo ngay khi gọi factory, không đợi TestClient lifespan.
   - `test_default_data_dir_uses_platformdirs`: thêm `monkeypatch.delenv("PHANTOM_DATA_DIR")` để fix env leak từ API test fixtures.
   - `test_health_auth.py`: `data_dir` fixture cleanup env sau yield để không làm ô nhiễm test khác.
2. **Xóa debug artifact**: `tests/api/test_debug_token.py` → `tests/api/debug_token.py` (không auto-discover pytest).
3. **pyproject.toml**: Thêm `fastapi>=0.115`, `uvicorn>=0.34`, `httpx>=0.28`.
4. **Step 3 bind validation**: Thêm `cmd_serve` CLI command với default `--host 127.0.0.1`, reject `0.0.0.0` trừ khi `--allow-remote`.
5. **Live smoke test**: start uvicorn → `/healthz` 200 ✓ → `/readyz` 403 (no token) ✓ → `/readyz` 200 (valid token) ✓ → `/v1/version` ✓ → `/openapi.json` schema OK ✓

**Files modified:**
- `src/phantom/api/app.py` — eager token gen
- `src/phantom/cli.py` — thêm `cmd_serve`
- `tests/api/test_health_auth.py` — env cleanup
- `tests/test_paths.py` — monkeypatch.delenv
- `tests/api/debug_token.py` — renamed (không auto-discover)
- `pyproject.toml` — FastAPI/uvicorn/httpx deps

**Verification:** **65/65 tests PASS**, API live smoke PASS.

---

### 2026-07-19 — Session 6: Windows hand-off ready (cross-compile + stop() port + ship script)

**Mục tiêu session:** đẩy Phase 2 tới "Windows hand-off ready" — binary Windows + sidecar Windows + `stop()` port + setup script để anh có thể chạy trên máy thật.

**Đã làm:**
1. **`stop()` Windows port** (`src/phantom/launcher.py`): thêm `IS_WINDOWS = platform.system() == "Windows"` module constant. Branch `stop()` ở đầu — Windows gọi `_stop_windows(profile_id, pid)` mới. Implement:
   - `_pid_dead_windows(pid)` dùng `ctypes.WinDLL("kernel32", use_last_error=True).OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE)` — nếu handle=0 + last_error=87 (`ERROR_INVALID_PARAMETER`) → pid không tồn tại (dead). Handle khác 0 → `GetExitCodeProcess` check `STILL_ACTIVE=259`.
   - `_kill_tree_windows(pid, force=True)` gọi `taskkill /T /F /PID <pid>` — `/T` kill cả tree descendant (Camoufox spawn Firefox contentproc + node driver đều con của pid ghi trong DB), `/F` = force SIGKILL-equivalent.
   - `_stop_windows()` kill + poll 4s cho process chết thật (không clear DB khi Firefox đang flush cookies).
   - `_descendants()` Windows return `[]` (taskkill /T lo rồi), `_reap_zombies()` Windows no-op (Win không có zombie concept như Linux).
2. **Verify Linux path không regress**: e2e launch profile 1 detached → sleep 5s cho Camoufox spawn đủ contentproc 7 cái + Xvfb 165510 + node driver 165501 → `stop 1` → post-stop pgrep chỉ còn Xvfb `:99` (chung cho app Tauri khác) + bash shell test, **0 orphan Camoufox/geckodriver/phantom.cli**. Sạch.
3. **Cross-compile Tauri Windows binary** từ Linux:
   - `rustup target add x86_64-pc-windows-gnu`
   - `apt-get install gcc-mingw-w64-x86-64`
   - `cargo check --target x86_64-pc-windows-gnu` → PASS 1m30s (compile `windows_x86_64_gnu`, `wry` 0.55.1, `tauri-runtime-wry` 2.11.4, `webview2-com` 0.38.2, all deps)
   - `cargo build --release --target x86_64-pc-windows-gnu` → PASS 3m19s, output `target/x86_64-pc-windows-gnu/release/tauri-app.exe` **23MB PE32+ GUI x86-64 (stripped to external PDB), 11 sections**
   - Copy sang `dist/windows/phantom-browser.exe` cho ship (cargo crate name vẫn là `tauri-app.exe`, tauri.conf productName đã đúng; mainBinaryName là field Tauri 3, không dùng Tauri 2)
4. **Rust lib.rs ship-branch** rewrite: bỏ `const REPO_ROOT: &str = "../../.."` hardcode. Thay bằng `repo_root()` runtime resolver — `PHANTOM_REPO` env override → dev `../../..` → ship `current_exe().parent()`. `sidecar_command(root)` trả `(python_path, vec!["-m","phantom.sidecar"])` với python path platform-specific: `<root>/.venv/Scripts/python.exe` Windows, `<root>/.venv/bin/python` Linux. Verifies: `cargo check` (Linux dev) clean + cross-compile Windows release clean.
5. **Ship strategy pivot**: PyInstaller không cross-build Linux→Windows (cần Win Python runtime + native deps lúc build). Thay bằng ship raw `.exe` Tauri + `scripts/windows-setup.ps1` PowerShell setup script — tạo `.venv`, `pip install -e .`, `camoufox sync + fetch` (1.2GB), smoke-test `python -m phantom.sidecar presets`. Cùng `.env.example`. Strategy đơn giản hơn, upgrade = `git pull` + `pip install -e .`.

**Files mới/sửa:**
- `src/phantom/launcher.py` — thêm `IS_WINDOWS`, `_pid_dead_windows`, `_kill_tree_windows`, `_stop_windows`, dispatch trong `stop()` + `_descendants()` + `_reap_zombies()` + `_pid_alive()`. Linux branch giữ nguyên.
- `tauri-app/src-tauri/src/lib.rs` — rewrite `sidecar_command()` + `sidecar_init()` + `sidecar_call()` dùng `repo_root()` runtime resolver. Bỏ `const REPO_ROOT`. Comment block cập nhật cross-compile note + ship strategy.
- `scripts/windows-setup.ps1` (new) — PowerShell setup cho tk's Windows machine.
- `.env.example` (new) — PROXY_1_* / PROXY_2_* template.
- `dist/windows/phantom-browser.exe` (new, 23MB) — cross-compiled binary ready to ship.

**Decisions locked (session 6):**
- **No PyInstaller — use setup script**. PyInstaller không cross-build Linux→Win. Ship raw `.exe` + .venv setup. Upgrade path = `git pull` + `pip install -e .`. Đơn giản, tránh staleness của bundled runtime.
- **Windows `stop()` dispatch runtime (python `platform.system()`)**, không phải `#[cfg(target_os="windows")]` compile-time. Vì 1 cross-compiled binary .exe + Linux dev build đều dùng chung code Python (interpreted), branch runtime là sạch sẽ.
- **`taskkill /T /F`** thay vì `OpenProcess`/`TerminateProcess` tree walk bằng tay. `/T` kill recursive tree đủ cho use case (Camoufox spawn đều là descendant thật của recorded pid). Nếu sau này gặp edge case không phải descendant → mới cần Toolhelp32 WalkTree.
- **`OpenProcess` + `GetExitCodeProcess` check `STILL_ACTIVE=259`** là Windows-equivalent của `kill -0`. Không dùng `tasklist /FI` (100ms+ spawn mỗi check + locale-dependent output).
- **`repo_root()` runtime resolver** thay vì `const REPO_ROOT`. Dev path `../../..` + ship path `exe_dir` khác nhau, không thể hardcode 1 giá trị cho cả 2. Override `PHANTOM_REPO` env cho debugging.

**Kết quả:** Phase 2 "Windows hand-off ready". Binary 23MB + setup script + `.env.example` sẵn sàng gửi sang tk. Anh chạy setup trên máy Windows → fill `.env` với real proxy → launch `phantom-browser.exe` → launch profile từ GUI → login FB/TikTok thật. Đó là human test cuối cùng.


### 2026-07-19 — Task 6: Engine adapter + worker event protocol ✅

**Task 6 mục tiêu:** Chuẩn hóa engine adapter (BaseEngine contract) và worker event protocol — một contract chung cho Camoufox hiện tại và Chromium tương lai.

**Đã làm:**
1. **Engine adapter base** (`src/phantom/engines/base.py`): Abstract base class với 9-method contract — `prepare`, `start`, `ready`, `navigate`, `snapshot`, `screenshot`, `cookies`, `storage_state`, `stop`. Mỗi method trả dict `{"status": ...}`.

2. **CamoufoxEngine adapter** (`src/phantom/engines/camoufox.py`): Wraps Camoufox (patched Firefox) behind BaseEngine contract. Giữ nguyên 6-blob persistent identity model; tái sử dụng `identity.build_launch_config()` để build fingerprint + config.

3. **Worker event protocol** (`src/phantom/workers/protocol.py`): Structured JSON events với sequence IDs (`seq`, `type`, `data`, `error`). `Event` class auto-increment seq, serialize/deserialize JSON. `validate_event_sequence()` reject out-of-order events.

4. **Worker main entry point** (`src/phantom/workers/main.py`): CLI entry `python -m phantom.workers.main --profile-id <id>`. Load profile, create engine, emit lifecycle events, heartbeat loop, graceful shutdown.

**Files mới:**
- `src/phantom/engines/{base.py,camoufox.py,__init__.py}` — engine adapter package
- `src/phantom/workers/{protocol.py,main.py,__init__.py}` — worker package
- `tests/test_engine_contract.py` — 22 tests

**Verification:**
- `pytest tests/test_engine_contract.py -v` → **22 passed in 0.43s**
- Full suite `pytest -q` → **141 passed in 3.02s** (up from 119 in Task 5)

**Decisions locked (Task 6):**
- **9-method contract** — đủ cho agent actions. Không expose full Playwright/CDP.
- **Worker sở hữu Playwright object** — không remote WS attach.
- **Event protocol dùng stdout one-JSON-per-line** — simplest cho ProcessRegistry (Task 7).
- **CamoufoxEngine giữ nguyên identity.build_launch_config** — 6-blob identity vẫn single source of truth.

---

---

### 2026-07-19 — Session 5: Phase 2 GUI shell scaffolded + e2e sidecar PASSED

**Mục tiêu session:** bắt đầu Phase 2 — Tauri + React GUI shell, bind `phantom` backend qua sidecar JSON-RPC. Skill ghi "Phase 2 next: Tauri GUI shell, Windows-only ship target, need cross-compile".

**Đã làm:**
1. **Install toolchain** (background, was slow): Rust 1.97.1 (rustup minimal), WebKitGTK 4.1 + libsoup-3.0 + javascriptcoregtk-4.1 + librsvg2-dev + libgtk-3-dev + pkg-config + libayatana-appindicator3-dev qua `apt-get`. `cargo install tauri-cli` killed half-way (compile từ source ~10p) — thay bằng `@tauri-apps/cli` 2.11.4 qua `npm install`, instant.
2. **Scaffold Tauri app** (`tauri-app/`) bằng `npm create tauri-app@latest -- --template react-ts --manager npm --identifier com.tk.phantombrowser`. Default template rồi edited conf + Cargo.toml + capabilities.
3. **Sidecar JSON-RPC layer** (`src/phantom/sidecar.py`): 9 actions (list/get/create/launch/stop/delete/status/log-tail/presets). Envelope `{ok, data}` / `{ok:false, error:{code,message,detail}}`. Exit 0 even on logical error. `_public_profile()` strips `proxy_pass` + 5 fingerprint blobs (GUI không cần). Error codes stable: `bad_args` / `not_found` / `bad_proxy` / `already_running` / `still_running` / `no_log` / `panic`. Contract spec written at `docs/sidecar-contract.md`.
4. **Rust bridge** (`src-tauri/src/lib.rs`): Tauri command `sidecar_call(action, args)` → load `.env` → spawn `.venv/bin/python -m phantom.sidecar` (dev branch) với `current_dir=REPO_ROOT` → parse stdout envelope → return `serde_json::Value`. Branch ship (`phantom-sidecar.exe`) để ngỏ. `sidecar_init` command load env vào State.
5. **React UI** (`src/App.tsx` + `src/sidecar.ts` types + `src/api.ts` wrappers + `App.css`):
   - Profile table: id / name / platform tag (color-coded) / proxy / tz / status pill (idle=gray / running=amber pulse)
   - Create form: name + platform + proxy + tz + notes, warns duplicate proxy count
   - Log drawer: chọn profile → poll `log-tail` 1.5s, badge "live" khi running
   - Toast notifications cho launch/stop/create/delete results
   - Dark goth theme (skull red accent #d44b3c, amber running, never pink/sparkly)
6. **Build verify:**
   - `cargo check` clean (1m30s first run)
   - `tsc --noEmit` clean
   - `vite build` clean (200KB JS, 5.5KB CSS)
   - `tauri build --no-bundle --debug` → binary 263MB at `src-tauri/target/debug/tauri-app`, ELF x86-64
7. **Xvfb setup** — start `Xvfb :99 -screen 0 1280x800x24` because Tauri uses WebKitGTK webview which needs a display. Launch app with `DISPLAY=:99 GDK_BACKEND=x11`. App alive, no crash.
8. **e2e sidecar flow test** (the real contract proof):
   - `status 1` before → idle (pid null)
   - `launch 1` → pid 163354 returned, log_path correct
   - 35s wait → `status 1` still running, pid matches
   - `log-tail 1 --bytes 4096` → reads launcher.log content `[phantom profile 1 running]` (append-mode log so also has old traceback from dead pid 135377 — không phải bug hiện tại, chỉ log cũ)
   - `stop 1` → stopped:true, previous_pid 163354
   - `status 1` → idle, pid null
   - orphan check: chỉ Xvfb :99 server còn (đúng), no Firefox/camoufox leak

**Files mới/sửa:**
- `src/phantom/sidecar.py` (new, 361 lines)
- `docs/sidecar-contract.md` (new, spec)
- `tauri-app/` (entire scaffold — `src-tauri/{Cargo.toml,tauri.conf.json,capabilities/default.json,src/lib.rs}`, `src/{App.tsx,App.css,sidecar.ts,api.ts,index.html}`)
- `src/phantom/launcher.py` (cosmetic comment clarifying stale-row clear logic — no behavior change)

**Decisions locked (session 5):**
- **Separate `sidecar.py` not `cli.py --json`** — keeps human CLI (`cli.py`, tk uses it) untouched; JSON-only sidecar file is easy to swap with PyInstaller standalone for Windows ship later.
- **Use `@tauri-apps/cli` npm package** (2.11.4) instead of `cargo install tauri-cli` — both work, npm is instant (prebuilt binary) vs cargo install ~10min source compile. Use `node_modules/.bin/tauri …` for all Tauri commands.
- **Xvfb display `:99`** is the canonical dev display for this repo when testing Tauri under headless Linux. App launched with `DISPLAY=:99 GDK_BACKEND=x11`.
- **Sidecar strips `proxy_pass` + all 6 fingerprint blobs** from `ProfilePublic` — GUI doesn't need them, reduces leak surface. `webgl:vendor` (visible in CLI list output) NOT shown in GUI yet (Phase 3 fingerprint viewer optional).
- **Polling not SSE for log-tail** — simplest contract: GUI polls `log-tail` every ~1.5s while status.running. Phase 2 streaming SSE = nice-to-have, not needed for MVP.

**False alarm during testing:** initially interpreted the first log-tail's `RuntimeError: already running as pid 135377` as a bug. Actually it's leftover log content from session 3/4 (launcher.log opens in append mode `'ab'`). `_pid_alive()` already returns False for dead pid → stale row cleared → launch succeeded. Patch added was harmless comment-only.

**Kết quả:** Phase 2 GUI shell scaffolded end-to-end. Sidecar contract stable + verified e2e. App boots alive under Xvfb. Contract ready for tk's Windows build (cross-compile) + interactive click testing next session.

---

### 2026-07-19 — Session 4: Phase 2 blockers solved (detached launch + cookie persist)

**Mục tiêu session:** verify 2 Phase 2 blockers đã implement ở session 3 thực sự chạy đúng — `launch_detached` (subprocess cho Tauri GUI) + cookie/session persistence (`persistent_context=True`). Skill ghi "blocker remaining" nhưng code đã có sẵn, chỉ chưa tested thật.

**Đã làm:**
1. **Clear stale state** — profile 1 stuck `status=running` từ session trước với dead pid 135377. `db.mark_stopped()` + `db.set_status('idle')`.
2. **Test cookie persistence** (`scripts/test_cookie_persistence.py`): launch 1 set marker cookie `phantom_marker=persist-<uuid>` tại `https://example.com` qua `document.cookie`. Launch 2 mở lại cùng origin mà không set → marker cookie vẫn còn. **PASS** — `persistent_context` + `user_data_dir` hoạt động đúng, cookies/localStorage/IndexedDB persist được qua nhiều launches.
3. **Test launch_detached** (`scripts/test_launch_detached.py`): spawn subprocess `python -m phantom.cli detached <id>` với `start_new_session=True`. Verify: parent return ngay (không block), child sống, DB ghi đúng child pid.
4. **Phát hiện + fix setsid bug trong `stop()`** — `start_new_session=True` khiến Camoufox tự spawn Xvfb với pgid riêng → `killpg(child_pgid)` miss nó, Xvfb orphan mỗi lần stop. Fix: `_descendants(parent_pid)` walk `/proc/<pid>/stat` find mọi descendant qua ppid chain (bất kể pgid), SIGTERM/SIGKILL từng pid explicit. `_pid_dead(pid)` check `/proc/<pid>` existence thay vì `kill -0` (zombie vẫn answer kill -0). Verify: child + Firefox + Xvfb all dead, no orphans.
5. **Probe script bug fix** — `verify_profile_determinism.py:probe_once()` raise KeyboardInterrupt từ probe để exit blocking loop, nhưng exception propagate ra ngoài `with Camoufox()` → caller không có wrapper → traceback. Wrap `launch_blocking()` call trong `try/except KeyboardInterrupt`.
6. **Re-run determinism probe** với persistent-context path (mặc định giờ `persistent=True`) → **16/16 keys + exit IP byte-identical**. Không regress.

**Kết quả:** Phase 2 blockers cleared. Cookie/session persist + detached launch + clean stop() hoạt động đúng. Code sẵn sàng cho Tauri GUI shell (Phase 2).

**Files mới/sửa:**
- `scripts/test_cookie_persistence.py` — probe cookie survival qua 2 launches.
- `scripts/test_launch_detached.py` — probe detached launch + stop() cleanup + orphan check.
- `src/phantom/launcher.py` — `_descendants()`, `_pid_dead()`, rewritten `stop()` (walk /proc, kill setsid'd grandchildren).
- `~/.hermes/skills/software-development/phantom-browser/scripts/verify_profile_determinism.py` — fix KeyboardInterrupt swallow trong `probe_once()`.

**Decisions locked (session 4):**
- Detached launch pattern: `subprocess.Popen(argv, start_new_session=True)` + child writes `launcher.log` + DB `running_instances` row hold child pid. `stop()` walk /proc (Linux) + killpg + kill-by-pid cho setsid'd grandchildren.
- Windows: `start_new_session` map sang `CREATE_NEW_PROCESS_GROUP` (cần verify Phase 2 build). `/proc` walk không có → fallback `taskkill /T` (kill tree) hoặc GetProcessHandle + WalkTree.
- `persistent_context=True` default cho mọi production launch. `persistent=False` chỉ cho throwaway probes (verify).

---

### 2026-07-19 — Session 3: Phase 1 backend MVP

**Mục tiêu session:** build Phase 1 MVP — backend Python (schema + CRUD + launch/stop) porting pattern từ spike_06 sang module dùng được, verify end-to-end.

**Đã làm:**
1. `schema.sql` — 2 bảng (profiles + running_instances) + indexes (platform_tag, status, proxy_host+port).
2. `db.py` — sqlite3 stdlib, WAL mode, foreign keys on, dict row factory. CRUD + `proxy_usage_count()` cho duplicate-proxy warning.
3. `identity.py` — port `reconstruct_fp()` + `generate_identity()` từ spike_04/06, trả 6 blobs (fingerprint_json, seeds_json, webgl_json, fonts_json, voices_json, misc_json). `build_launch_config(profile)` dựng full config từ persisted blobs — đây là chỗ gọi `launch_options` thay _em_, đây là thứ duy nhất giữ determinism.
4. `presets.py` — facebook/tiktok/chatgpt/custom. Hiện vẫn luôn spoof windows (mobile profile = Phase 3 TODO).
5. `launcher.py` — `launch_blocking()` (hold Camoufox context, probe callback, await Ctrl+C), `stop()` (SIGTERM + SIGKILL fallback), `probe_identity()` (ip-api + navigator + WebGL + screen).
6. `cli.py` + `__main__.py` + `pyproject.toml` — `python -m phantom.cli {init,create,list,show,launch,verify,stop,delete}`.
7. Test end-to-end: create fb-test-1 với proxy 1 → list → verify → **2 launches ra 16/16 keys identical** + exit IP stable. Duplicate-proxy warning + delete path cũng OK.

**Kết quả:** Phase 1 backend MVP usable. Fingerprint persistence (load-bearing insight #2) giữ qua 2 launches giờ được verify trong code production chứ không chỉ spike. Phase 2 (Tauri shell) có thể bắt đầu.

**Files mới:** `src/phantom/{__init__.py,schema.sql,db.py,identity.py,presets.py,launcher.py,cli.py,__main__.py}`, `pyproject.toml`, `profiles.db`, `profiles_data/`.

---

### 2026-07-19 — Session 2: fix BUG-1 canvas drift + close BUG-2/3/4

**Mục tiêu session:** fix BUG-1 (canvas signature đổi giữa các runs) — blocker cuối cho fingerprint determinism trước khi vào Phase 1.

**Đã làm (theo thứ tự):**

1. **Đọc skill `phantom-browser` + session_search** để nạp context đầy đủ (plan, Phase 0 state, BUG-list, dev env).
2. **Đọc source Camoufox** `fingerprints.py` + `utils.py:launch_options()` (lines 459–866) để hiểu flow build config. Phát hiện: `launch_options` gọi `set_into(..., randint)` cho seeds + `_generate_random_font_subset` / `_generate_random_voice_subset` / `sample_webgl` mỗi launch khi chưa pre-set.
3. **Spike 05** (`spike_05_dump_config_diff.py`) — monkey-patch `set_into` / `merge_into` để track mọi write vào config qua 2 lần gọi `launch_options()`. Diff phát hiện **5 drifted keys**: `webGl:vendor`, `webGl:renderer`, `webGl:parameters`, `webGl2:parameters` (Intel vs NVIDIA mỗi launch) và `window.history.length` (3 vs 5).
4. **Spike 06** (`spike_06_fix_canvas_stable.py`) — apply fix full-lock: persist `webgl.json`, `fonts.json`, `voices.json`, `misc.json` (window.history.length + window.screenY) + pin timezone/locale/navigator language + `ff_version='152'` + `headless='virtual'` (Xvfb).
5. **Spike 07** (`spike_07_full_config_diff.py`) — dump CAMOU_CONFIG_1 env var (final config gửi tới Firefox binary) 2 lần, JSON-diff. Kết quả: **49/49 keys byte-identical, 0 drift** sau fix spike_06. Trước đó từng là `locale:language` drift (en/es random từ GeoIP `from_region`), `window.screenY` drift (handle_screenXY randrange) — cả 2 đã lock.
6. **Verify canvas thực tế** (spike_06 run browser 3 lần) — config 100% stable nhưng canvas cross-process hash vẫn khác. Bằng chứng quyết định: **same-page 3x draws trong 1 process → identical hash** → browser deterministic trong process → drift giữa process là backend rendering nondeterminism (Firefox Software WebRender / Cairo trên Linux headless không GPU). Không phải bug fingerprint.
7. **Xvfb discovery** — `headless=True` → WebGL disabled (tell). `headless='virtual'` (Xvfb) → WebGL enabled, `WEBGL_debug_renderer_info` trả đúng locked vendor/renderer. Server không có GPU thật nên WebGL software render, nhưng vendor/renderer spoof đúng profile.
8. **Patch skill `phantom-browser`** — thêm "THE load-bearing insight #2" với full-lock pattern + Xvfb + canvas Linux constraint, update verification checklist.

**Kết quả:** Phase 0 ~95%. BUG-1/2/4 SOLVED, BUG-3 partial-fix + root-caused, chỉ còn BUG-5 (proxy residential — verify Phase 3) và BUG-6 mới (canvas Linux headless constraint — verify Phase 2 Windows build). Phase 1 không còn blocker.

**Files mới:** `spike/spike_05_dump_config_diff.py`, `spike/spike_06_fix_canvas_stable.py` (reference impl cho Phase 1 `launch()`), `spike/spike_07_full_config_diff.py`, persisted identity blobs (`spike/webgl.json`, `fonts.json`, `voices.json`, `misc.json`).

**Decisions locked (session 2):**
- Fingerprint identity pattern: fingerprint JSON + seeds + webgl + fonts + voices + misc, all persisted per-profile, build full `config=` dict before calling `launch_options`/`Camoufox`.
- Linux dev env dùng `headless='virtual'` (Xvfb) để có WebGL, không phải `headless=True`.
- Canvas determinism không block Phase 1 — fingerprint config đã đúng, chỉ không verify được trên Linux server.

### 2026-07-19 — Session 1: spike 01–04, phát hiện BUG-1

(Xem chi tiết ở các mục `Phase 0 status` + `Closed bugs` phía dưới. Session 1 đã làm: setup venv, fetch Camoufox 152.0.4-beta.28, spike 01–04 (engine / proxy / test sites / stable seeds). Phát hiện BUG-1 trở thành blocker.)

---

## Closed bugs

### ✅ BUG-1 — Canvas signature đổi giữa các runs (root cause pinned)

**Root cause:** KHÔNG phải fingerprint config. Sau khi lock tất cả 48 config keys (webgl vendor/renderer/parameters, fonts, voices, window.history.length, window.screenY, timezone, locale:language/region, navigator.language/languages, seeds), `launch_options()` final config **49/49 keys byte-identical across runs** (verify bằng spike_07 full diff). Canvas hash vẫn drift giữa các browser process khác nhau.

**True root cause:** Firefox Software WebRender / Cairo font rasterizer trên **Linux headless không có GPU** là nondeterministic ở pixel-level — mỗi process sinh ra pixel canvas hơi khác nhau do font hinting/anti-aliasing nondeterminism. Bằng chứng quyết định:

- Cùng fingerprint + cùng config → 3 process khác nhau → 3 canvas hash khác
- Cùng fingerprint + cùng process → vẽ canvas 3 lần trong cùng page → **3 hash identical** (browser deterministic trong 1 process)

**Implication:** Canvas stability **không thể** verify trên Linux server này. Config đã đúng 100%, đây là backend rendering issue, không phải fingerprint. Test canvas determinism phải chờ build Windows binary chạy trên máy tk có GPU thật. Phase 1 có thể build — fingerprint identity đã stable.

**Partial fixes đã apply (giảm drift ở những chỗ có thể):**
- Lock `webGl:vendor` + `webGl:renderer` + toàn bộ `webGl:parameters` một lần (sample_webgl('win') trả dict đầy đủ, persist nguyên dict vào `webgl.json`). `launch_options` thấy 2 key vendor/renderer đã có trong config → bỏ qua `sample_webgl(target_os)` random path, dùng sample_webgl(target_os, vendor, renderer) lookup exact hoặc merge directly.
- Lock `fonts` list (40 families) qua `_generate_random_font_subset('windows')` 1 lần, persist `fonts.json`.
- Lock `voices` list (`_generate_random_voice_subset('windows')`), persist `voices.json`.
- Lock `window.history.length` (randint 1-5) + `window.screenY` (randint trong range availHeight-outerHeight) qua `misc.json`.
- Pin `locale:language='en'`, `locale:region='US'`, `navigator.language='en-US'`, `navigator.languages=['en-US']` → kill GeoIP `from_region` random language (locales.py:271 np.random.choice).

### ✅ BUG-2 — Firefox version mismatch (FIXED)

`from_browserforge(fp, ff_version='152')` → navigator.userAgent giờ là `Firefox/152.0`, khớp binary.

### ✅ BUG-4 — Timezone geoip mismatch (FIXED)

`config['timezone'] = 'America/Denver'` set trước → GeoIP `as_config()` dùng `setdefault` (utils.py:756) nên value của mình win. Browser show TZ = `America/Denver`, exit IP geo cũng `America/Denver`. Lệch 1h Denver/Chicago hết.

### 🔄 BUG-3 — WebGL disabled trên Linux headless (ROOT CAUSED + PARTIAL FIX)

**Symptom cũ:** `headless=True` → browserleaks báo "supported, disabled or unavailable", `WEBGL_debug_renderer_info` trả null.

**Fix partial:** `headless='virtual'` (Xvfb) → WebGL **enabled**, `WEBGL_debug_renderer_info` trả đúng locked vendor `Google Inc. (NVIDIA)` + renderer `ANGLE (NVIDIA, NVIDIA GeForce GTX 980 Direct3D11 vs_5_0 ps_5_0), or similar`. Server không có GPU thật nên WebGL vẫn chạy software, nhưng vendor/renderer spoof là đúng profile.

**Còn chờ:** Test trên Windows binary thật với GPU → WebGL sẽ render bằng GPU vật lý, không còn Software WebRender. Cho đến lúc đó thì WebGL-as-identity đã verified: vendor/renderer gửi đi giống nhau giữa các launch (vì lock trong config).

## Open bugs

> Chỉ còn lại BUG-5 — không blocker cho Phase 1.

### BUG-5 — Proxy residential chưa verify (VERIFY)

2 proxy của tk exit tại Kalispell US, ISP = "Mobite Network LLC" (AS399861). Check trên ipqualityscore.com / proxycheck.io / scamalytics xem có bị flag datacenter/VPN không. Phase 3 (multi-acc thật cho FB/TikTok) phải có residential sạch. Phase 1 MVP không cần.

### BUG-6 (MỚI) — Canvas determinism không verify được trên Linux headless

Không phải bug code mà là environment constraint. Canvas cross-process drift vì Firefox Software WebRender nondeterministic ở headless Linux không GPU. Phase 1 build tiếp, verify canvas cuối trên Windows build.

---

## Next steps (khi pick lại)

1. **Task 16 — NEXT:** xây stealth coherence gate theo authoritative plan, dùng raw schema Task 15 và controlled TLS/HTTP2 capture; không promote Clearcote trước khi Linux headed + native Windows gates xanh.
2. **Task 13 — IMPLEMENTED / PENDING WINDOWS CI:** PyInstaller `--onedir`, Tauri MSVC/NSIS + portable ZIP workflow đã có; cần run `windows-latest` thật rồi mới DONE. Không có Windows claim từ session này.
3. **Task 14 — DONE ON LINUX:** parent recreate container sau hai fix runtime (`PHANTOM_DATA_DIR=/data`; named-volume bootstrap cần tối thiểu `DAC_OVERRIDE,FOWNER` cùng CHOWN/SETUID/SETGID). Container healthy; token đúng `/data/runtime/.api_token`, user 10001 đọc được; authenticated `scripts/smoke-linux.sh` PASS; `docker compose -p phantomtask14c down --timeout 20` xóa container/network; robust `/proc` scan thấy 0 orphan `uvicorn phantom.api.app` và `Xvfb :99`. AppImage/DEB local build chưa chạy, nhưng Linux CI workflow tồn tại.
4. **Task 15 — DONE:** probe viết test/schema trước, rồi chạy stock Chromium 148, Clearcote 149 pre.22 và fingerprint-chromium 148 trên Linux; cả ba PASS persistent UDD/CDP. Raw JSON/checksums + ADR chọn Clearcote *experimental only*, Camoufox vẫn default, không auto-fallback. Donut/Wayfern reject cho core adapter vì app coupling/AGPL + terms riêng. Windows asset chỉ audit availability, không claim execution.
5. Canvas determinism Windows GPU thật và residential proxy reputation vẫn là acceptance/manual gates riêng.

---

## Skill/lessons learned

- **BrowserForge Fingerprint không có native `loads`/`from_dict`** — phải rebuild nested dataclasses thủ công (`NavigatorFingerprint(**d['navigator'])`, etc.). Helper đã có ở `spike/spike_0{1,2,4,6}_*.py:reconstruct_fp()`.
- **BrowserForge cũng không support seeded generation** — pattern đúng cho persistent identity: generate 1 lần → `fp.dumps()` → store JSON → reconstruct. KHÔNG regenerate mỗi launch.
- **`from_browserforge(fp)` KHÔNG cast `videoCard` → `webGl:vendor`/`webGl:renderer`** — đây là root cause BUG-1 phiên đầu. BrowserForge có `Fingerprint.videoCard` (vendor, renderer) nhưng `_cast_to_properties(BROWSERFORGE_DATA)` không map 2 field này vào `webGl:*` config keys. Result: `launch_options` thấy thiếu → random `sample_webgl(target_os)` mỗi launch → random vendor + matching parameters. Fix: gọi `sample_webgl('win')` 1 lần, persist nguyên dict vào `webgl.json`, merge vào config trước khi chạy `launch_options`.
- **Camoufox `config=` param** là cách đúng để inject seeds / custom properties (CAMOU_CONFIG_1 env var). `set_into` chỉ no-op KHI key đã có trong config trước, nên config phải được build trước khi pass.
- **`launch_options()` random mỗi launch:** `webGl:*` (sample_webgl), `fonts` (`_generate_random_font_subset`), `voices` (`_generate_random_voice_subset`), `window.history.length` (randrange 1-5), `window.screenY` (handle_screenXY randrange), `locale:language` (GeoIP `from_region` np.random.choice). Muốn deterministic phải **pre-set tất cả** vào `config=` trước, KHÔNG chỉ fingerprint obj + 3 seeds.
- **`launch_options()` không có tham số `timezone` hay `locale` keyword** — phải set qua `config['timezone']` / `config['locale:language']` / `config['navigator.language']`. GeoIP sau đó chỉ `setdefault` (không override), nên giá trị mình set wins.
- **`headless='virtual'` qua Xvfb** enable WebGL trên server Linux không GPU (Software WebRender). Vendor/renderer spoof vẫn đúng. Canvas cross-process vẫn drift do font rasterizer nondeterministic — KHÔNG fix được trên Linux headless, chỉ verify được trên Windows binary + GPU thật.
- **`from_browserforge(fp, ff_version='152')`** sửa UA `Firefox/150.0` → `Firefox/152.0` khớp binary.
- **proxy dict format** cho Camoufox: `{"server": "http://host:port", "username": "u", "password": "p"}` (KHÔNG phải URL form).
- **Canvas determinism test pattern:** trong cùng page vẽ canvas 3 lần, hash 3 lần. Nếu 3 hash giống nhau = browser deterministic trong process (OK). Nếu khác nhau giữa các process = backend rendering nondeterminism (Linux headless only, không phải fingerprint bug).
- CreepJS là fingerprint detector comprehensive nhất (`abrahamjuliot.github.io/creepjs/`), cần `networkidle` wait + 8s delay vì JS async.

Potential skill để save sau `phantom-browser-camoufox` — đợi Phase 1 xong rồi tạo skill 1 lần cho cả workflow.
