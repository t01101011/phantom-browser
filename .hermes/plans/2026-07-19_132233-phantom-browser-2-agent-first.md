# Phantom Browser 2.0 — Vision-like, Agent-first Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Chuyển Phantom từ prototype Tauri gọi Python theo từng command thành browser control plane local-first, Windows-first nhưng Linux-ready, có GUI kiểu Vision và API/MCP tối ưu cho agent.

**Architecture:** Tauri + React chỉ là desktop client. Python FastAPI là control plane duy nhất, sở hữu SQLite, worker registry, event stream và agent API. Mỗi session chạy trong worker process biệt lập qua engine adapter; Camoufox giữ vai trò engine ổn định hiện tại, còn Chromium engine-level được spike sau dựa trên Clearcote/Donut thay vì JS injection.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite/WAL, psutil, Camoufox/BrowserForge, Tauri 2, React/TypeScript, pytest, GitHub Actions; Windows Job Objects và Linux process groups/systemd cgroups; MCP Streamable HTTP ở pha sau.

**Linux primary use case:** Linux là agent runtime trên VPS, không phải desktop port cho đủ checklist. Browser session phải chạy persistent trong headed-virtual display để agent tự động login/actions, đồng thời hỗ trợ viewer/noVNC và human takeover cho CAPTCHA, 2FA, passkey hoặc challenge không thể tự động hóa an toàn.

---

## Guardrails và quyết định khóa

1. Không sao chép source, branding hay assets độc quyền của Vision; chỉ tái tạo capability từ public docs.
2. Không tuyên bố parity với Vision cho real-device corpus, UDP SOCKS5, webcam spoofing hay TLS persona nếu chưa có test thực nghiệm.
3. Không dùng JS/CDP injection làm engine antidetect chính. Chromium track phải engine-level và qua coherence gate.
4. Camoufox worker giữ quyền sở hữu Playwright object. Remote WS của Camoufox là experimental, không được làm dependency bắt buộc của core API.
5. Chromium mới được trả CDP endpoint; Camoufox trả transport/action capability đúng thực tế.
6. Release Windows phải build/test trên `windows-latest` MSVC; Linux build/test trên Linux. Không dùng Linux→Windows GNU cross-build làm release chính.
7. Mọi feature code đi theo RED→GREEN→REFACTOR; mỗi task có test và commit riêng.

## Success criteria của milestone đầu

- Windows installer/portable mở được GUI và chạy control plane mà không cần user tự tạo `.venv`.
- Linux chạy được API headless không cần Tauri; desktop package là client tùy chọn.
- VPS agent có thể login và thao tác qua action API; cùng session mở được bằng secured viewer để người dùng takeover rồi trả quyền lại cho agent mà không mất cookie/storage/profile.
- Persistent profile start/stop/restart giữ cookie và fingerprint.
- Instant session tự xóa data sau stop nhưng trả cookies/storage artifacts.
- Agent có thể create/lease/heartbeat/operate/release session qua versioned API.
- Worker crash được phát hiện; process tree sạch; DB không kẹt `running`.
- API bind `127.0.0.1`, token bắt buộc, secrets không xuất hiện trong response/log.

---

### Task 1: Đóng băng behavior hiện tại bằng characterization tests ✅ DONE 2026-07-19

**Execution result:** 21/21 tests xanh. Coverage gồm DB CRUD/WAL/FK/running cleanup, 6-blob launch-config determinism, 9 sidecar actions/envelopes/redaction, launcher detached/state. TDD bắt được và fix một regression Windows thật: duplicate `_pid_alive()` ở cuối `launcher.py` đã đè mất implementation dispatch qua `_pid_dead_windows()`. Production `phantom.cli verify fb-test-1` chạy hai lần cho cùng exit IP và navigator/screen/WebGL output byte-identical. Audit note: `scripts/verify_profile_determinism.py` hiện thiếu trong repo dù tài liệu nhắc tới; CLI verify được dùng làm integration gate tạm thời.

**Objective:** Có safety net trước khi thay sidecar/control plane.

**Files:**
- Create: `tests/test_db_profiles.py`
- Create: `tests/test_identity_persistence.py`
- Create: `tests/test_sidecar_contract.py`
- Create: `tests/test_launcher_state.py`
- Modify: `pyproject.toml`

**Steps:**
1. Viết test cho create/get/update/delete, WAL và running row cleanup.
2. Viết test reconstruct 6 identity blobs và hai lần `build_launch_config()` byte-identical.
3. Viết test envelope/error codes của 9 sidecar actions hiện tại.
4. Viết launcher tests với fake worker process, không launch browser thật.
5. Chạy `pytest tests -q`; ghi baseline failures nếu là bug thật, không sửa test để che lỗi.
6. Commit: `test: characterize existing phantom backend`.

**Verification:** `pytest tests -q` xanh; determinism probe thực vẫn để ở integration marker.

---

### Task 2: Tách settings, paths và secrets khỏi project directory ✅ DONE 2026-07-19

**Execution result:** thêm `paths.py` dùng `platformdirs` + `PHANTOM_DATA_DIR`, tạo layout `profiles/artifacts/runtime/phantom.db`; migrate DB, launcher và sidecar khỏi runtime paths tương đối; thêm recursive secret redaction cho proxy URL/token/public payload; thêm dependency `platformdirs`. Verification: 43/43 tests xanh, default CLI tạo/đọc DB ở platform data dir và override smoke tạo đúng `$PHANTOM_DATA_DIR/phantom.db`. TDD verification của parent bắt thêm một bug từ implementation đầu: SQLite fail `unable to open database file` khi platform data dir chưa tồn tại; `get_conn()` giờ mkdir parent trước khi connect.

**Objective:** Một data layout cross-platform dùng được ở desktop lẫn service.

**Files:**
- Create: `src/phantom/settings.py`
- Create: `src/phantom/paths.py`
- Create: `tests/test_paths.py`
- Modify: `src/phantom/db.py`
- Modify: `src/phantom/launcher.py`
- Modify: `pyproject.toml`

**Steps:**
1. RED: test `PHANTOM_DATA_DIR` override và default qua `platformdirs`.
2. Implement `data_dir`, `profiles_dir`, `artifacts_dir`, `db_path`, `runtime_dir`.
3. Migrate callers khỏi relative paths; không tự động move data cũ trong task này.
4. Thêm redaction helper cho proxy password/token trong logs và public models.
5. GREEN: unit tests + existing suite.
6. Commit: `refactor: centralize cross-platform paths and settings`.

---

### Task 3: Thiết kế schema v2 và migration idempotent ✅ DONE 2026-07-19

**Execution result:** thêm migration ledger + runner transaction-safe và migration additive `0002_control_plane.sql` cho `folders`, `proxies`, `sessions`, `session_leases`, `events`, `artifacts`; bảng `profiles` cũ chỉ được bổ sung nullable `folder_id`/`proxy_id`, không xóa field hay làm hỏng sidecar legacy. Có indexes cho session profile/status, lease expiry và event/artifact creation time. Tests cover empty DB, fixture v1 giữ nguyên profile/secrets, rerun schema byte-equivalent, required indexes và SQLite backup/restore. Verification cuối: **49/49 tests PASS**, `PRAGMA foreign_key_check` rỗng, `integrity_check=ok`, CLI init + sidecar list smoke PASS; wheel audit xác nhận bundle cả `schema.sql` và `migrations/*.sql`.

**Objective:** Lưu profiles, folders, proxies, sessions, leases, events và artifacts có versioning.

**Files:**
- Create: `src/phantom/migrations/0002_control_plane.sql`
- Create: `src/phantom/migrations.py`
- Create: `tests/test_migrations.py`
- Modify: `src/phantom/schema.sql`
- Modify: `src/phantom/db.py`

**Tables tối thiểu:** `folders`, `proxies`, `profiles_v2` hoặc columns migration tương thích, `sessions`, `session_leases`, `events`, `artifacts`, `schema_migrations`.

**Steps:**
1. RED: migrate empty DB và DB v1 fixture; chạy migration hai lần phải không đổi.
2. Implement transaction + schema version.
3. Thêm indexes cho `profile_id/status`, `lease_expires_at`, `created_at`.
4. Không xóa bảng/fields v1; sidecar legacy vẫn đọc được trong giai đoạn chuyển tiếp.
5. GREEN: migration tests + backup/restore DB fixture.
6. Commit: `feat: add versioned control-plane schema`.

---

### Task 4: Xây FastAPI control plane tối thiểu có token auth

**Objective:** Thay command-per-process bằng server local lâu dài mà chưa bỏ sidecar.

**Files:**
- Create: `src/phantom/api/__init__.py`
- Create: `src/phantom/api/app.py`
- Create: `src/phantom/api/auth.py`
- Create: `src/phantom/api/models.py`
- Create: `src/phantom/api/routes_health.py`
- Create: `tests/api/test_health_auth.py`
- Modify: `pyproject.toml`

**Endpoints:** `GET /healthz`, `GET /readyz`, `GET /v1/version`.

**Steps:**
1. RED: `/healthz` public; `/readyz` và `/v1/*` yêu cầu bearer/local token; compare constant-time.
2. Implement app factory và random token persisted with owner-only permissions where supported.
3. Bind mặc định `127.0.0.1`; reject `0.0.0.0` unless explicit insecure/remote config.
4. OpenAPI có schema nhưng docs chỉ local.
5. GREEN: TestClient suite.
6. Commit: `feat: add authenticated local control plane`.

---

### Task 5: Port profile/folder/proxy CRUD sang REST v1

**Objective:** GUI, CLI và agent dùng cùng một contract.

**Files:**
- Create: `src/phantom/api/routes_profiles.py`
- Create: `src/phantom/api/routes_folders.py`
- Create: `src/phantom/api/routes_proxies.py`
- Create: `src/phantom/services/profile_service.py`
- Create: `src/phantom/services/proxy_service.py`
- Create: `tests/api/test_profiles.py`
- Create: `tests/api/test_folders_proxies.py`

**Endpoints:** CRUD `/v1/profiles`, `/v1/folders`, `/v1/proxies`; clone profile; bulk import preview/apply.

**Steps:**
1. RED theo từng endpoint: validation, conflict, not-found, secret redaction.
2. Implement service layer transaction-safe; route không gọi SQL trực tiếp.
3. Folder defaults gồm engine, extensions, bookmarks/start pages chỉ là schema placeholder, chưa implement runtime.
4. Proxy health endpoint trả structured result; không log credential.
5. GREEN: API tests.
6. Commit: `feat: expose profile folder and proxy APIs`.

---

### Task 6: Chuẩn hóa engine adapter và worker event protocol

**Objective:** Một contract cho Camoufox hiện tại và Chromium tương lai.

**Files:**
- Create: `src/phantom/engines/base.py`
- Create: `src/phantom/engines/camoufox.py`
- Create: `src/phantom/workers/protocol.py`
- Create: `src/phantom/workers/main.py`
- Create: `tests/test_engine_contract.py`
- Modify: `src/phantom/launcher.py`

**Contract:** `prepare`, `start`, `ready`, `navigate`, `snapshot`, `screenshot`, `cookies`, `storage_state`, `stop`; structured JSON events with sequence IDs.

**Steps:**
1. RED: fake engine phải pass adapter contract; malformed/out-of-order events bị reject.
2. Move Camoufox launch config behind adapter, giữ nguyên 6-blob identity.
3. Worker owns Playwright/Camoufox objects; control plane không attach remote WS để điều khiển core.
4. Keep legacy launcher wrapper gọi adapter trong transition.
5. GREEN: unit tests + `scripts/verify_profile_determinism.py` integration.
6. Commit: `refactor: introduce engine worker contract`.

---

### Task 7: ProcessRegistry cross-platform và crash recovery

**Objective:** Quản lý nhiều worker an toàn, sạch process tree.

**Files:**
- Create: `src/phantom/runtime/registry.py`
- Create: `src/phantom/runtime/process_windows.py`
- Create: `src/phantom/runtime/process_linux.py`
- Create: `tests/runtime/test_registry.py`
- Create: `tests/runtime/test_crash_recovery.py`
- Modify: `src/phantom/launcher.py`

**Steps:**
1. RED: duplicate launch conflict, ready timeout, crash event, stale DB reconciliation, stop-all.
2. Registry giữ handles in-memory và sessions trong DB; startup reconcile dead PIDs.
3. Windows: Job Object `KILL_ON_JOB_CLOSE`, fallback `taskkill /T /F`.
4. Linux: new process group; service deployment dựa vào systemd `KillMode=control-group`; giữ `/proc` descendant cleanup fallback.
5. Emit heartbeat, resource stats, exit reason.
6. GREEN: fake-process tests trên mọi OS; platform tests chạy trong CI native.
7. Commit: `feat: add cross-platform worker registry`.

---

### Task 8: Persistent sessions API và SSE event stream

**Objective:** Profile session trở thành first-class resource như Vision/Steel.

**Files:**
- Create: `src/phantom/api/routes_sessions.py`
- Create: `src/phantom/api/routes_events.py`
- Create: `src/phantom/services/session_service.py`
- Create: `tests/api/test_sessions.py`
- Create: `tests/api/test_events.py`

**Endpoints:** `POST /v1/profiles/{id}/sessions`, `GET /v1/sessions`, `GET/DELETE /v1/sessions/{id}`, `GET /v1/sessions/{id}/events` (SSE).

**Steps:**
1. RED: state machine `starting→ready→stopping→stopped|crashed`.
2. Implement idempotency key cho start/stop.
3. Return capability descriptor: `actions` cho Camoufox; không ghi giả `cdp_url`.
4. SSE support resume bằng sequence/Last-Event-ID.
5. Add max concurrency + FIFO queue + start timeout.
6. GREEN: API and concurrency tests.
7. Commit: `feat: add persistent browser sessions`.

---

### Task 9: Instant sessions, leases, TTL và artifacts

**Objective:** Agent chạy tác vụ tạm an toàn, tự cleanup và lấy output.

**Files:**
- Create: `src/phantom/api/routes_instant.py`
- Create: `src/phantom/api/routes_leases.py`
- Create: `src/phantom/api/routes_artifacts.py`
- Create: `src/phantom/services/lease_service.py`
- Create: `tests/api/test_instant_sessions.py`
- Create: `tests/api/test_leases.py`

**Endpoints:** `POST /v1/sessions/instant`, lease acquire/heartbeat/release, screenshot/cookies/storage artifacts.

**Steps:**
1. RED: instant dir deleted after stop; cookies/storage returned or exported; TTL expires session.
2. Implement owner token, lease generation and monotonic heartbeat semantics.
3. Add artifact size/type limits and retention cleanup.
4. Crash must still cleanup temp dir after artifact finalization attempt.
5. GREEN: fake-clock tests, crash tests, traversal/security tests.
6. Commit: `feat: add instant leased sessions and artifacts`.

---

### Task 10: Agent action API và token-efficient snapshots

**Objective:** Agent thao tác không cần raw HTML hay tự viết Playwright code.

**Files:**
- Create: `src/phantom/api/routes_actions.py`
- Create: `src/phantom/agent/snapshot.py`
- Create: `src/phantom/agent/actions.py`
- Create: `src/phantom/agent/watchdogs.py`
- Create: `tests/agent/test_snapshot_refs.py`
- Create: `tests/agent/test_actions.py`

**Actions:** navigate, snapshot, click, type, press, scroll, select, screenshot; element refs có generation/version.

**Steps:**
1. RED: accessibility/DOM fixture serialize thành stable refs; stale ref trả explicit error.
2. Implement snapshot gồm interactive elements, visibility, role/name/value; không gửi full DOM mặc định.
3. Add navigation/popup/download/crash watchdog events.
4. Humanized input v1 chạy ở controller với seeded timing/path; ghi rõ không tương đương custom engine CDP của Vision.
5. GREEN: fixture tests và headed integration smoke.
6. Commit: `feat: add agent actions and indexed snapshots`.

---

### Task 11: MCP Streamable HTTP adapter

**Objective:** Hermes/coding agents gọi Phantom trực tiếp mà không nhân đôi logic REST.

**Files:**
- Create: `src/phantom/mcp/server.py`
- Create: `src/phantom/mcp/tools.py`
- Create: `tests/mcp/test_tools.py`
- Modify: `src/phantom/api/app.py`

**Steps:**
1. RED: MCP tools map 1:1 vào service methods, auth và lease rules giống REST.
2. Tools tối thiểu: list/create profile, start/stop/lease session, navigate/snapshot/click/type/screenshot.
3. Mount Streamable HTTP `/mcp`; không mở stdio daemon thứ hai ở milestone đầu.
4. Tool responses compact, structured, có error codes.
5. GREEN: protocol tests.
6. Commit: `feat: expose agent tools over MCP`.

---

### Task 12: Chuyển React GUI từ Tauri command sang HTTP control plane ✅ DONE 2026-07-20

**Execution result:** React GUI dùng REST/SSE chung với agents: Bearer token chỉ nhận qua Tauri IPC và giữ trong memory, CRUD profile/folder/proxy, search/filter, edit/clone, proxy health, start/stop/session drawer và durable SSE reconnect (`Last-Event-ID`). Rust bootstrap chạy đúng một loopback control plane, đợi authenticated `/readyz`, giữ child handle và kill/wait khi app drop; dev Python path có override rõ ràng, packaging standalone được để đúng Task 13. Audit bắt và sửa 3 lỗi runtime thật: adapter gọi `Camoufox` context manager như browser object, direct profile vẫn truyền proxy URL rỗng, SSE parser không chịu CRLF/malformed event. Verification: frontend **5/5**, Python **210/210**, Rust **3/3**, TypeScript/Vite và Tauri debug build PASS. Live Xvfb control-plane/Camoufox smoke đạt `ready`, trả action capabilities không CDP, stop `stopping`, cleanup không orphan. WebView binary boot + child lifecycle PASS; browser automation chỉ inspect Vite UI vì browser ngoài Tauri không có IPC, nên không claim native click-through/Windows.

**Objective:** GUI Vision-like dùng đúng API mà agents cũng dùng.

**Files:**
- Modify: `tauri-app/src/api.ts`
- Modify: `tauri-app/src/App.tsx`
- Modify: `tauri-app/src/App.css`
- Create: `tauri-app/src/features/profiles/*`
- Create: `tauri-app/src/features/sessions/*`
- Create: `tauri-app/src/features/proxies/*`
- Create: `tauri-app/src/features/folders/*`
- Create: frontend tests theo test runner được thêm
- Modify: `tauri-app/src-tauri/src/lib.rs`

**Steps:**
1. RED: API client auth, error and reconnect tests.
2. Tauri starts packaged control-plane sidecar once, waits `/readyz`, injects base URL + token.
3. Implement sidebar/folders, searchable profile table, create/edit/clone, proxy test, status/session drawer và SSE logs.
4. Keep design functionally inspired by Vision; không copy brand/assets/layout pixel-for-pixel.
5. Remove direct `sidecar_call` usage only after parity tests pass.
6. GREEN: frontend build/tests + Tauri dev smoke.
7. Commit: `feat: connect desktop UI to control plane`.

---

### Task 13: Windows release pipeline native

**Objective:** Installer và portable artifact thực sự được test trên Windows.

**Files:**
- Create: `.github/workflows/release-windows.yml`
- Create: `packaging/phantom-sidecar.spec`
- Create: `scripts/smoke-windows.ps1`
- Modify: `tauri-app/src-tauri/tauri.conf.json`
- Modify: `scripts/package-windows.py` hoặc retire sau khi CI thay thế

**Steps:**
1. RED: CI smoke script fail nếu thiếu sidecar, WebView2 loader, frontend assets hoặc `/readyz`.
2. Build Python sidecar `--onedir`; collect Camoufox/BrowserForge/Playwright data, excludes deps nặng không dùng.
3. Build Tauri `x86_64-pc-windows-msvc` trên `windows-latest`; create NSIS + portable ZIP.
4. Run binary, wait ready, call health/profile/instant smoke, verify process cleanup.
5. Generate SHA256SUMS and upload artifacts.
6. Commit: `ci: build and smoke-test Windows releases`.

---

### Task 14: Linux VPS agent runtime và desktop artifacts ✅ DONE ON LINUX 2026-07-20

**Execution result:** Docker/systemd/noVNC/human-takeover/Linux release workflow đã implement. Acceptance container thật được parent chạy sau audit/fix hai lỗi: compose đặt `PHANTOM_DATA_DIR=/data` để token/state vào volume đúng, và root bootstrap named volume cần capability tối thiểu `DAC_OVERRIDE,FOWNER` bên cạnh CHOWN/SETUID/SETGID. Recreate container healthy; `/data/runtime/.api_token` đọc được bằng user 10001; authenticated `scripts/smoke-linux.sh` PASS. `docker compose -p phantomtask14c down --timeout 20` xóa container/network; scan `/proc` tránh self-match xác nhận 0 orphan `uvicorn phantom.api.app`/`Xvfb :99`. Release workflow đọc token explicit bằng user 10001. AppImage/DEB chưa build local nhưng workflow CI tồn tại; không claim artifact chưa chạy.

**Objective:** Linux là runtime chính cho agents trên VPS: tự động login/actions trong persistent headed-virtual sessions, có human takeover khi challenge; desktop package chỉ là client phụ.

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `packaging/phantom.service`
- Create: `packaging/novnc/README.md`
- Create: `scripts/smoke-linux.sh`
- Create: `.github/workflows/release-linux.yml`
- Create: `tests/integration/test_human_takeover.py`
- Modify: `tauri-app/src-tauri/tauri.conf.json`

**Steps:**
1. RED: container/API smoke chạy không cần Tauri; persistent headed-virtual smoke dùng Xvfb/Wayland.
2. Docker image chạy control plane + worker, non-root, persistent volumes, adequate `/dev/shm`, healthcheck.
3. Thêm secured viewer/noVNC chỉ bind loopback mặc định; truy cập ngoài qua SSH/Tailscale/reverse tunnel có auth, không public port trần.
4. Implement takeover lease: agent pause input → human điều khiển cùng browser process → human release → agent reacquire sau fresh snapshot.
5. systemd unit dùng `KillMode=control-group`, restart policy và state dir.
6. Build AppImage + `.deb` cho desktop client; API service vẫn chạy độc lập và là sản phẩm Linux chính.
7. Test login fixture, takeover/release, crash cleanup, cookie persistence và artifacts trên Linux CI. CAPTCHA/real third-party login là manual acceptance test, không cố bypass trong CI.
8. Commit: `ci: add Linux agent runtime and desktop releases`.

---

### Task 15: Spike Chromium engine-level, không commit kiến trúc mù ✅ DONE 2026-07-20

**Execution result:** viết schema/probe + RED tests trước candidate install; probe explicit binary/persistent UDD/CDP reconnect/relaunch và raw UA/UA-CH, main/Worker, GPU, fonts, canvas/audio/rects, WebRTC, TLS/HTTP2 status. Linux chạy binary thật stock Playwright Chromium 148, Clearcote 149 pre.22 và fingerprint-chromium 148: cả ba PASS persistence + CDP; raw JSON và SHA-256 được lưu. Audit license/assets/cadence gồm Clearcote BSD-3 (Linux/Windows signed/checksummed assets), fingerprint-chromium BSD metadata, Donut AGPL + Wayfern terms/coupling. ADR chọn Clearcote chỉ làm adapter experimental sau Task 16; Camoufox vẫn default, engine explicit, không auto-fallback. Không claim Windows execution; TLS/HTTP2 controlled capture, full ServiceWorker và GPU thật chuyển đúng Task 16. Full suite 213/213 PASS.

**Objective:** Chọn Chromium backend dựa trên real measurements.

**Files:**
- Create: `spikes/chromium-engine/README.md`
- Create: `spikes/chromium-engine/probe.py`
- Create: `docs/chromium-engine-decision.md`
- Test candidates: Clearcote, Donut/Wayfern, fingerprint-chromium theo license/build availability.

**Acceptance matrix:** Windows+Linux binary availability; persistent user-data-dir; CDP attach/reconnect; UA/UA-CH; worker-main; WebGL/WebGPU; fonts; canvas/audio/client rects; WebRTC/DNS; TLS/HTTP2; update cadence; license.

**Steps:**
1. Write probe and expected schema before installing candidate.
2. Run same probe against stock Chromium baseline and candidates.
3. Record raw outputs/checksums, not marketing scores.
4. Reject JS-injection-only candidates for default antidetect engine.
5. Write ADR selecting adapter or deferring engine; no auto-fallback between engines without explicit profile setting.
6. Commit: `spike: evaluate engine-level Chromium backends`.

---

### Task 16: Stealth coherence gate và release acceptance ✅ DONE LINUX 2026-07-20

**Execution result:** gate normalized deterministic + fixtures RED/GREEN, same-profile relaunch, main/DedicatedWorker/SharedWorker/ServiceWorker, UA/UA-CH, GPU, screen, locale/geo, fonts, WebRTC và transport status. Controlled local stock Chromium Linux chạy thật và raw/verdict/SHA256 được archive; kết quả `conditional_pass` vì WebGPU adapter attestation và TLS/HTTP2 controlled capture ghi `unsupported`, tuyệt đối không đổi thành PASS. Geo unit gate offline; network probe chỉ informational. Linux và Windows release workflows chạy gate + upload evidence. **Task 13 vẫn IMPLEMENTED/PENDING native Windows CI; không claim Windows.**

**Objective:** Không release engine change nếu fingerprint drift hoặc cross-surface inconsistency.

**Files:**
- Create: `tests/stealth/test_worker_main.py`
- Create: `tests/stealth/test_ua_ua_ch.py`
- Create: `tests/stealth/test_gpu_coherence.py`
- Create: `tests/stealth/test_locale_geo.py`
- Create: `scripts/stealth-coherence.py`
- Modify: release workflows

**Checks:** same profile across relaunch; main vs Worker/SharedWorker/ServiceWorker; UA vs UA-CH; WebGL vs WebGPU; screen/viewport; timezone/locale/proxy geo; font list/metrics; WebRTC leak; TLS/HTTP2 capture where feasible.

**Steps:**
1. RED against stock/misconfigured fixtures.
2. Implement deterministic report + thresholds.
3. Run local engine integration; archive report as CI artifact.
4. Block release on deterministic/coherence regressions; external anti-bot websites remain informational, not sole gate.
5. Commit: `test: gate releases on fingerprint coherence`.

---

## Deferred until core is proven

- Team/cloud sync and RBAC.
- Extension library, per-folder bookmarks/start pages beyond schema.
- Input synchronizer across profiles.
- Real-device fingerprint corpus.
- SOCKS5 UDP/QUIC relay, proxy traffic cache.
- Webcam/video spoofing.
- Automatic engine fallback.
- macOS release.

Human takeover/viewer trên VPS không nằm trong deferred list; đó là acceptance requirement của Linux agent runtime.

## Validation matrix

| Layer | Required checks |
|---|---|
| Unit | DB/migrations, identity, adapters, registry, leases, snapshots, auth |
| API | OpenAPI contract, idempotency, SSE resume, concurrency/backpressure, redaction |
| Engine integration | persistent cookies, same-profile determinism, instant cleanup, crash cleanup |
| Windows release | installer + portable cold start, ready probe, launch/stop, no orphan process |
| Linux service | Docker/systemd health, headless action, Xvfb headed launch, cgroup cleanup |
| Stealth | worker/main, UA-CH, WebGL/WebGPU, fonts, WebRTC, locale/geo, TLS persona |
| Agent | MCP tools, lease expiry, stale refs, screenshots/artifacts, compact snapshots |

## Research references

- `research/antidetect-technical-research.md`
- `research/agent-first-browser-research.md`
- `research/crossplatform-build-release.md`
- `docs/reference-project-audit.md`
- `docs/vision-gap-matrix.md`
- `docs/phantom-foxdesk-vision-gap-matrix.md`
- `docs/agent-profile-browser-architecture.md`
- Vision public docs: https://docs.browser.vision/
- Clearcote patches: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches
- Donut Browser: https://github.com/zhom/donutbrowser
- FoxDesk: https://github.com/BB0813/foxdesk
- Browserless: https://github.com/browserless/browserless
- Steel Browser: https://github.com/steel-dev/steel-browser
- Browser Use: https://github.com/browser-use/browser-use
- BrowseForge: https://github.com/nczz/BrowseForge
