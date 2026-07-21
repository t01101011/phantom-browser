# Phantom Browser — Plan

> Antidetect browser với profile manager GUI, tự host, để nuôi/quản lý multi-account.
> Status: Phase 2 hand-off ready · Priority: Low · Deadline: 2026-07-24 · TAG: TK (side project)
> Notion project: `399539c8-7ba9-811c-9b07-d0f19fb583ce`
> Discord: `#phantom-browser` (category PERSONAL, channel `1525126316662198404`)

---

## Mục tiêu

App desktop chạy trên **Windows + Linux** để quản lý **50–100 browser profile**, mỗi
profile là một danh tính độc lập (fingerprint riêng, proxy riêng, cookie/session
riêng), phục vụ multi-account. Login tay qua GUI, không headless.

Không cạnh tranh Multilogin/AdsPower — mục tiêu là bản tự host đủ dùng cho nhu cầu
cá nhân, khỏi trả phí subscription.

### Product target cập nhật — Vision-like, agent-first

Target chức năng là một bản local-first tương đương nhóm tính năng cốt lõi của
Vision Browser, không sao chép source/branding/assets độc quyền: GUI quản lý
profile/folder/proxy cho người dùng, cộng local HTTP API ổn định cho agent.
Windows và Linux là first-class; Linux phải chạy được cả desktop headed lẫn
headless service/container. Gap matrix và thứ tự triển khai nằm tại
`docs/vision-gap-matrix.md`.

---

## Quyết định kiến trúc (đã chốt sơ bộ)

| Layer | Chọn | Lý do |
|---|---|---|
| Browser engine | **Camoufox** (patched Firefox) | Spoof fingerprint ở tầng C++, không phải JS-injection → khó bị bắt. Bundle sẵn **BrowserForge** sinh fingerprint *coherent* từ dữ liệu máy thật. Open-source thật (MPL-2.0), maintain đều. |
| App shell | **Tauri** (Rust + web frontend) | Một codebase build ra cả Windows + Linux, nhẹ hơn Electron nhiều. tk muốn thử desktop app. |
| Frontend GUI | React (hoặc Svelte) trong Tauri webview | Bảng profile, launch/stop, gán proxy, tag/status. |
| Profile store | **SQLite** | id, fingerprint seed, proxy, đường dẫn cookie, platform tag, status, notes. |
| Engine driver | **Python sidecar** chạy Camoufox | Tauri gọi sidecar (qua stdio/HTTP local) để launch Camoufox với config của từng profile. |

**Sơ đồ:**
```
Tauri (Rust shell) ──► React GUI (bảng profile, nút Launch)
        │
        ├──► SQLite (profiles.db)
        │
        └──► Python sidecar ──► Camoufox.launch(user_data_dir, proxy, fingerprint_seed)
                                     └─ BrowserForge sinh fingerprint coherent
```

---

## Vì sao Camoufox lo được phần khó nhất

Phần khó của antidetect KHÔNG phải GUI — mà là **fingerprint coherent**: UA khớp
platform, WebGL vendor khớp OS, screen/timezone/locale/fonts khớp nhau và khớp IP
của proxy. Lệch một chỗ là lộ. Đây là thứ các sản phẩm thương mại bán (họ có DB
fingerprint máy thật).

Camoufox + BrowserForge giải sẵn: mỗi profile lưu 1 **seed fingerprint**, engine
tự dựng ra một danh tính nhất quán từ dữ liệu thật. Camoufox cũng tự match
timezone/locale theo GeoIP của proxy. → Mình chỉ viết lớp quản lý bên trên.

Điểm yếu cần biết: Camoufox nền **Firefox** → vài site chỉ-Chromium có thể fail.
Nếu về sau cần Chromium, cân nhắc `fingerprint-chromium` (adryfish) làm engine thứ 2.

---

## Proxy — thứ quyết định 70% sống chết  ⚠️

App xịn mà proxy rác thì vẫn chết. Ghi chú:
- Mỗi profile **1 proxy residential cố định** (1:1). **Đừng dùng datacenter** cho
  FB/TikTok — chết ngay.
- Field proxy per-profile là **bắt buộc** trong schema.
- Cần chốt **nguồn proxy** trước khi phần proxy trong app finalize: nhập tay từng
  cái / import list / tích hợp API nhà cung cấp. → **TODO: tk xác nhận nguồn proxy.**
- App nên cảnh báo nếu > X profile share cùng 1 IP.

---

## Custom theo từng sàn (logic app phải build)

Fingerprint thì Camoufox lo, nhưng mỗi platform soi một kiểu → gom lại thành mấy
preset per-profile:

**Nhóm 1 — gắt nhất (Facebook, TikTok):** soi machine fingerprint bền theo thời
gian + hành vi + IP "cư trú". Cần residential proxy cố định, **warm-up từ từ**
(đừng tạo 100 acc bấm login loạt), giữ cookie/session cực bền. TikTok soi cả
canvas/WebGL + device motion + timing, nhiều khi phải giả **profile mobile**.

**Nhóm 2 — vừa (Google, sàn TMĐT):** chủ yếu IP + cookie. Google hay bắt verify
SĐT khi nhiều acc cùng IP. TMĐT chống multi-acc bằng SĐT/địa chỉ/thẻ trùng — cái
đó là dữ liệu tk nhập, ngoài tầm browser.

**Nhóm 3 — dễ (forum, web thường):** fingerprint khác + IP khác là xong.

→ Rút gọn thành các trường config per-profile:
- `proxy` (loại + endpoint) — quan trọng nhất
- `platform_tag` (fb/tiktok/google/…) → preset fingerprint hợp lý (desktop vs mobile, locale)
- `timezone/locale` auto-match theo IP proxy (bật tính năng có sẵn của Camoufox)
- `status` (sống/chết/đang warm), `notes`
- cookie/session lưu bền per-profile

---

## Roadmap

**⚠️ EXECUTION AUDIT 2026-07-19 —** Task 1 của plan Phantom 2.0 đã hoàn thành: thêm 21 characterization tests cho DB CRUD/WAL/FK/running cleanup, 6-blob identity determinism, đủ 9 sidecar parser actions + JSON envelope/redaction, và launcher detached/state behavior. Test-first còn bắt được bug thật: `launcher.py` định nghĩa `_pid_alive()` hai lần; bản Linux-only ở cuối file đè mất nhánh Windows, nên duplicate-launch check trên Windows sai. Đã xóa duplicate và giữ implementation cross-platform. `pytest -q` xanh 21/21; hai lần production `phantom.cli verify fb-test-1` cho cùng exit IP và toàn bộ navigator/screen/WebGL probe byte-identical. Drift phát hiện: script `scripts/verify_profile_determinism.py` được plan/skill nhắc tới nhưng không tồn tại trong repo; hiện verification dùng CLI production path, script wrapper sẽ được phục hồi khi refactor Task 6 chạm engine adapter.

**⚠️ EXECUTION UPDATE 2026-07-19 —** Task 2 hoàn thành: runtime data chuyển sang `platformdirs` với `PHANTOM_DATA_DIR` override; DB/launcher/sidecar dùng layout chung; có secret redaction; test suite tăng lên 43/43. Parent verification bắt và fix lỗi first-run `unable to open database file` bằng cách tạo parent data directory trước SQLite connect. Không tự move `profiles.db` cũ theo đúng scope của plan.

|**⚠️ EXECUTION UPDATE 2026-07-19 —** Task 3 hoàn thành: schema control-plane v2 được triển khai bằng additive, versioned migrations; giữ nguyên bảng/fields v1 và bổ sung folders, proxies, sessions, leases, events, artifacts cùng indexes runtime. Migration chạy transaction-safe, idempotent, migrate fixture v1 không mất dữ liệu và backup/restore được. Verification cuối **49/49 tests PASS**, SQLite integrity/FK sạch, CLI + sidecar smoke PASS, wheel chứa đủ SQL migration assets. Bước tiếp theo là Task 4 — FastAPI control plane tối thiểu có token auth.

**⚠️ EXECUTION UPDATE 2026-07-19 —** Task 4 hoàn thành: FastAPI app factory + token auth (load_or_generate_token eager), public /healthz, auth /readyz + /v1/version, bind 127.0.0.1 default, reject 0.0.0.0 trừ --allow-remote. Fix 3 test failures (token eager eval, env leak, debug artifact rename). Verification: **65/65 tests PASS**, uvicorn live smoke: /healthz 200, /readyz 403 (no token) / 200 (valid token), /v1/version OK.

**⚠️ EXECUTION UPDATE 2026-07-19 —** Task 5 hoàn thành: service layer + REST endpoints + API tests cho profile/folder/proxy full CRUD. Service layer transaction-safe với optional conn kwarg. Clone profile giữ proxy/timezone/locale, fresh identity (6-blob). Bulk import preview + apply (single transaction). Proxy health check qua urllib → httpbin.org/ip, ghi health_status, không log credential. Secret redaction verified: proxy_pass/fingerprint blobs absent, proxy password = *****. Verification cuối: **119/119 tests PASS**, live REST smoke 32/32 PASS (auth, profile/folder/proxy CRUD, clone, import, health, deletion).

**⚠️ EXECUTION UPDATE 2026-07-20 —** Audit Tasks 1–7 hoàn tất an toàn: Task 6 contract/parser/legacy wrapper/determinism tests và Task 7 runtime/crash cleanup đều xanh trên Linux; Windows native Job Object/browser smoke vẫn pending. Task 8 hoàn thành persistent sessions REST + durable SSE resume, idempotent start/stop, action capability descriptor không giả CDP, concurrency/FIFO và startup reconciliation. Verification cuối **192/192 tests PASS**, TypeScript/Vite/Rust PASS, live uvicorn HTTP/SSE smoke PASS. Boundary: không chạy lại production Camoufox determinism (script wrapper vẫn thiếu/live launch bị giới hạn); chỉ giữ evidence production trước đó, không claim kết quả mới.

**⚠️ EXECUTION UPDATE 2026-07-20 —** Task 9 hoàn thành instant disposable sessions, owner leases/generation/monotonic heartbeat, TTL reaper, safe artifact metadata/storage/redaction/retention và cleanup stop/crash/reconcile. Verification **196/196 tests PASS**; live uvicorn HTTP/TTL/artifact smoke PASS bằng no-process adapter (TTL `stopped`, temp dir deleted, secret redacted). Windows/native browser không được claim.

**⚠️ EXECUTION UPDATE 2026-07-20 —** Task 10 hoàn thành indexed compact snapshots, generation-scoped stale refs, lease-guarded REST actions, popup/download/crash watchdogs và controller-side seeded humanized typing. Verification **202/202 tests PASS**; headed Chromium/Xvfb fixture smoke PASS (snapshot/type/click/stale-ref/screenshot). Không claim native Camoufox/Windows.

**⚠️ EXECUTION UPDATE 2026-07-20 —** Task 11 hoàn thành MCP Streamable HTTP `/mcp` trong cùng control plane: Bearer auth dùng chung token REST, session/SSE lifecycle chuẩn SDK, 10 tools tối thiểu dùng trực tiếp profile/session/lease/action services, structured errors và không quảng cáo CDP URL. TDD protocol **4/4 PASS**, full Python **206/206 PASS**; live uvicorn initialize/list-tools/create-profile/error/DELETE smoke PASS, auth thiếu token 403.

**⚠️ EXECUTION UPDATE 2026-07-20 —** Task 12 hoàn thành migration GUI từ command-per-process sang HTTP REST/SSE. UI có sidebar/folder filter, search, profile create/edit/clone/delete, proxy create/test/delete, start/stop, session capabilities/log drawer; token chỉ qua Tauri IPC/in-memory, không URL/storage/log. Rust boot một loopback child, authenticated readiness, kill/wait khi drop. Audit sửa Camoufox context-manager lifecycle, direct-profile empty proxy và SSE CRLF/malformed/reconnect handling. Verification: frontend **5/5**, Python **210/210**, Rust **3/3**, Vite/TSC/Tauri debug build PASS; live Xvfb API + Camoufox session đạt `ready`, stop/cleanup không orphan. WebView binary boot verified; interactive browser chỉ inspect Vite shell do browser ngoài Tauri không có IPC. Task 13 chưa triển khai: cần native `windows-latest`, không claim Windows từ Linux.

**⚠️ EXECUTION UPDATE 2026-07-20 —** Task 13 **DONE / NATIVE WINDOWS ACCEPTED**: `release-windows.yml` run `29781059924` xanh toàn bộ 18 steps trên `windows-latest`; packaged sidecar smoke, MSVC/NSIS build, portable smoke, NSIS install smoke, checksums và artifact upload đều PASS. Artifact `phantom-browser-windows-x64` tồn tại, không expired, kích thước 1,038,990,400 bytes; Task 16 Windows evidence cũng được upload. Task 14 **DONE ON LINUX** với authenticated Docker smoke thật: fix `PHANTOM_DATA_DIR=/data`, named-volume root bootstrap capabilities, token `/data/runtime/.api_token` user 10001, healthy container, smoke PASS và `/proc` cleanup 0 orphan; AppImage/DEB local chưa chạy. Tasks 15–16 DONE ON LINUX; Task 16 Windows CI gate cũng PASS nhưng unsupported surfaces vẫn giữ nguyên unsupported, không relabel thành pass. Full Python baseline gần nhất **225/225 PASS**.

**CURRENT PLAN — Phantom 2.0 (research synthesis 2026-07-19):**
`.hermes/plans/2026-07-19_132233-phantom-browser-2-agent-first.md` là implementation plan authoritative. Các phase cũ bên dưới chỉ là lịch sử của prototype v0.1.

### Kiến trúc đã chốt cho milestone tiếp theo

- Giữ Tauri + React làm desktop client, **không** giữ command-per-process sidecar làm control plane.
- Thêm Python FastAPI local control plane có token auth; GUI, CLI và agents dùng chung REST/SSE contract.
- Mỗi browser session là worker process biệt lập qua engine adapter + ProcessRegistry.
- Giữ Camoufox + 6-blob persistent identity làm engine đầu tiên. Worker sở hữu Playwright object; Camoufox remote WS experimental không phải core dependency.
- Chromium là track engine-level riêng, spike Clearcote/Donut/fingerprint-chromium rồi mới chọn. Không dùng JS/CDP injection làm antidetect engine chính.
- Windows-first nhưng core cross-platform: release Windows build/test native trên `windows-latest`; Linux có headless API/service trước, desktop AppImage/deb sau.
- Agent-first: persistent + instant sessions, lease/heartbeat/TTL, idempotency, SSE events, artifacts, indexed accessibility snapshots và MCP Streamable HTTP.
- **Linux primary use case:** chạy browser workers trên VPS để agent tự động login và thực hiện actions. Desktop Linux GUI chỉ là phụ; VPS phải có persistent headed-virtual sessions (Xvfb/Wayland), API/MCP, browser viewer/noVNC để human takeover khi gặp CAPTCHA/2FA, và reconnect mà không làm mất profile state.

### Roadmap Phantom 2.0

- [x] **P0 — Safety/control plane:** characterization tests; cross-platform paths; schema migrations; FastAPI health/auth; profile/folder/proxy CRUD.
- [x] **P1 — Runtime:** engine adapter; structured worker protocol [Task 6]; ProcessRegistry; crash recovery; Windows Job Objects + Linux process-group/cgroup cleanup [Task 7]. Linux verified; native Windows packaged launch/stop/process-cleanup smoke accepted in Task 13 CI.
- [x] **P2 — Sessions/agents:** persistent sessions + SSE; instant sessions; leases/TTL/idempotency; screenshots/cookies/storage; indexed snapshots/actions; MCP; VPS viewer + human takeover cho login challenge.
- [x] **P3 — Product GUI:** React dùng HTTP control plane; folders, profile edit/clone/import, proxy health, session/log views.
- [ ] **P4 — Native releases:** Task 13 Windows pipeline DONE/native CI accepted; Task 14 Linux runtime DONE; AppImage/deb local chưa chạy.
- [x] **P5 — Chromium spike:** stock/Clearcote/fingerprint-chromium probe + ADR; Clearcote experimental only, không auto-fallback.
- [x] **P6 — Stealth gate:** worker/main, UA-CH, WebGL/WebGPU, fonts, WebRTC, locale/geo, TLS/HTTP2 coherence checks wired into release; Windows evidence uploaded, unsupported surfaces remain explicit.

### Deferred

Team/cloud sync, extension library, synchronizer, real-device corpus, SOCKS5 UDP/QUIC, proxy cache, webcam/video spoofing và macOS chỉ làm sau khi core/runtime/release gates ổn. Human takeover trên VPS **không deferred** vì là requirement của login automation.

**⚠️ AUDIT 2026-07-19 —** Roadmap gốc phía dưới đã stale: Phase 0, Phase 1 và phần code/build của Phase 2 đều đã hoàn thành. Windows release đã cross-compile; Python sidecar được setup tại máy đích bằng PowerShell vì PyInstaller không thể cross-build Linux → Windows. Việc còn lại của Phase 2 là smoke test trên máy Windows thật: setup venv, mở GUI, launch/stop một profile và verify fingerprint/cookie.

**⚠️ RE-AUDIT 2026-07-19 —** Windows hand-off đã lộ hai lỗi packaging liên tiếp (thiếu `WebView2Loader.dll`, release mở nhầm Vite `localhost`). Dừng mở rộng Tauri shell cho tới khi benchmark implementation đã ship thật. Reference chính được chọn để audit là **FoxDesk** (`BB0813/foxdesk`): cùng Camoufox + Python backend, có GUI Windows, PyInstaller/Inno Setup, GitHub Actions chạy trên `windows-latest`, portable ZIP + installer release và test suite. Mirage Browser dùng Electron/CDP sẽ là reference phụ cho UX/profile manager, không dùng làm fingerprint engine chuẩn vì spoof qua JS/CDP yếu hơn Camoufox native patch.

### Phase 0 — Spike / xác minh (0.5–1 ngày)
- [x] Cài Camoufox, launch thử 1 instance với proxy + fingerprint seed cố định.
- [x] Verify fingerprint qua 2–3 site test (creepjs, browserleaks, pixelscan).
- [x] Xác nhận cùng persisted identity → cùng fingerprint qua nhiều lần mở (deterministic).

### Phase 1 — MVP backend (Python) (2–4 ngày)
- [x] Schema SQLite + persistent identity blobs + running-instance tracking.
- [x] CRUD profile.
- [x] `launch(profile_id)` / `stop(profile_id)` — mở Camoufox đúng data-dir + proxy + identity; Linux verified, Windows path implemented.
- [x] Cookie/session persist per-profile (data-dir riêng).

### Phase 2 — GUI Tauri + React (3–5 ngày)
- [x] Bảng profile: tên, platform, proxy, status, nút Launch/Stop.
- [x] Form tạo profile (chọn platform preset, dán proxy).
- [x] Bind frontend ↔ Python JSON sidecar.
- [x] Build Linux + cross-compile Windows release.
- [ ] Smoke test tương tác trên máy Windows thật: setup, GUI launch/stop, cookie/fingerprint.

### Phase 3 — Chất lượng multi-acc (1–2 tuần, làm dần)
- [ ] Import proxy theo list / theo file.
- [ ] Cảnh báo trùng IP.
- [ ] Group/tag profile, bulk launch.
- [ ] Cookie import/export.
- [ ] (Optional) Warm-up scheduler cho nhóm gắt.
- [ ] (Optional) Engine Chromium thứ 2 (fingerprint-chromium) cho site chỉ-Chromium.

**Ước lượng:** MVP dùng được ~1–2 tuần. Bản đầy đủ ~1–2 tháng.

---

## Ghi chú build/test
- Backend Python + logic có thể dev & test trên server Linux (Trang làm được).
- **Bản chạy thật phải cài trên máy tk** (có màn hình) — login acc là mở browser bấm tay,
  server headless không login được. Trang sẽ hướng dẫn cài từng bước khi tới lúc đó.

## Quyết định đã chốt (19/07/2026)

1. **Nguồn proxy**: nhập tay per-profile + hỗ trợ API IPRoyal (pull list động). Proxy field trong schema tách rõ `source` (manual / iproyal / file) để sau import list.
2. **Sàn ưu tiên**: Social media (FB/TikTok — nhóm gắt nhất) + **ChatGPT** (nhóm 2, chủ yếu cookie + IP). Preset đầu tiên làm: `facebook`, `tiktok`, `chatgpt`. ChatGPT cần verify SĐT — ghi chú riêng.
3. **Target build**: **Windows trước** (use case chính ở máy tk), nhưng control plane/runtime cross-platform từ đầu. Linux gồm cả headless service/container và desktop client; không còn chỉ là môi trường dev fingerprint.

### Testing strategy — Linux dev env → Windows ship

Server Linux headless **không thể test login tay** nên phân ranh giới rõ:

| Việc | Linux (server Trang) | Windows (máy tk) |
|---|---|---|
| Camoufox engine + BrowserForge fingerprint determinism (creepjs/browserleaks/pixelscan, không cần login) | ✅ Dev + verify | ✅ Cross-check một lần cuối |
| Python sidecar (launch/stop/profile CRUD/proxy plumbing) | ✅ Dev + test | ✅ Verify chạy đúng path Win |
| Tauri shell build (Windows binary) | ❌ Không dùng làm release path | ✅ Build/test native qua Windows CI + final test máy tk |
| Login tay FB/TikTok/ChatGPT, warm-up | ❌ Không làm được | ✅ Chỉ có ở đây |

Quy tắc: **Linux env xác nhận phần kỹ thuật fingerprint + proxy đúng**, Windows build chỉ check "chạy được không + có same fingerprint không" — không để làm pha login test trên server.

Release chính sẽ build trên Windows CI (MSVC/NSIS) và smoke-test artifact native trước khi chuyển cho tk. Linux release có pipeline riêng; Linux→Windows GNU cross-compile chỉ còn giá trị compile probe, không phải artifact ship.

---

## Proxy hiện có
- tk có sẵn 2 proxy residential (sẽ dùng để test Phase 0 spike ngay). Chi tiết proxy nhập vào `.env` hoặc `profiles.local.json` (không commit).

---

## Tham chiếu — landscape open-source (research 2026-07-19)

- **Product/desktop:** Donut Browser (Tauri cross-platform), FoxDesk (Camoufox + FastAPI + Windows packaging), Vision public docs (capability/API benchmark).
- **Agent infrastructure:** Browserless, Steel Browser, Browser Use, BrowseForge và Playwright MCP.
- **Engines:** Camoufox/BrowserForge cho Firefox hiện tại; Clearcote, Donut/Wayfern và fingerprint-chromium cho Chromium engine-level spike.
- **Nguyên tắc:** engine-level patch + single coherent persona seed; JS/CDP injection chỉ có thể là automation compatibility layer, không phải stealth foundation.
- Research đầy đủ: `research/antidetect-technical-research.md`, `research/agent-first-browser-research.md`, `research/crossplatform-build-release.md`.
