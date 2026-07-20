# Kiến trúc Profile Browser Agent-First — Cross-Platform (Windows + Linux)

## Tổng quan

Tài liệu này phân tích các ràng buộc kỹ thuật, đề xuất kiến trúc dual-engine theo pha (phased), và chiến lược kiểm thử cho một hệ thống **antidetect profile browser** tối ưu cho autonomous agents, chạy trên cả Windows và Linux.

---

## Phần 1: Phân tích Công nghệ Nền

### 1.1 Camoufox — Firefox fork chống phát hiện

| Thuộc tính | Giá trị |
|---|---|
| Engine gốc | Firefox (fork C++, patch fingerprint ở tầng engine) |
| Giao thức tự động hóa | **Juggler** (Mozilla custom protocol, *không phải* CDP) |
| API native | Python (`Camoufox` / `AsyncCamoufox`) |
| Dung lượng | ~200MB (headless, đã gỡ telemetry/bloat) |
| Mã nguồn | Mở hoàn toàn từ v146.0.1-beta.25 (01/2026) |
| OS hỗ trợ | Windows, macOS, Linux |

**Cơ chế stealth:**
- Sửa fingerprint ở tầng C++ — không inject JavaScript → không để lại dấu vết
- Juggler bị patch để sandbox Playwright Page Agent → trang web không thể phát hiện automation
- Dùng BrowserForge để sinh fingerprint theo phân phối thực tế (market share)
- WebGL, fonts, WebRTC, screen, timezone, locale, geoIP — tất cả đều được spoof đồng bộ

### 1.2 Ràng buộc kết nối Camoufox + Playwright

#### Native API (Python)
```python
from camoufox.sync_api import Camoufox
with Camoufox() as browser:
    page = browser.new_page()
    page.goto("https://example.com")
```
- Hoạt động hoàn hảo trong Python
- Hỗ trợ `persistent_context=True` + `user_data_dir` cho profile
- Headless: `True` (native) hoặc `"virtual"` (Xvfb)

#### Remote Server (WS Endpoint)
```bash
python -m camoufox server  # mặc định
# Hoặc trong code:
from camoufox.server import launch_server
launch_server(port=1234, ws_path='hello', headless=True, ...)
# → ws://localhost:1234/hello
```
**Client kết nối từ bất kỳ ngôn ngữ nào:**
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.firefox.connect('ws://localhost:1234/hello')
    page = browser.new_page()
```

#### ⚠️ Ràng buộc / Hạn chế QUAN TRỌNG

| Hạn chế | Chi tiết |
|---|---|
| **1 browser instance / server** | Remote server chỉ chạy 1 trình duyệt → fingerprint không xoay vòng |
| **Experimental** | Camoufox ghi rõ: "This feature is experimental. It uses a hacky workaround to gain access to undocumented Playwright methods." |
| **Không giữ context khi connect lại** | Issue #209: Khi dùng `p.firefox.connect()`, `browser.contexts` trả về **rỗng** ([]), khác với Chromium `connectOverCDP` giữ được context |
| `persistent_context` không hoạt động với remote server | Dùng `persistent_context=True` + `user_data_dir` trong `launch_server` không giải quyết được vấn đề tái sử dụng session |
| **Juggler vs CDP** | Juggler không hỗ trợ `connectOverCDP` — chỉ có `connect()` thông qua WebSocket |
| **Chỉ 1 fingerprint/server** | Nếu cần fingerprint rotation ở quy mô lớn, phải chạy nhiều server hoặc dùng Pool mode |

#### Camoufox Connector (pim97/camoufox-connector)
- WS bridge: Python server → HTTP API → WS endpoint → Playwright clients (Node.js, Go, Java, .NET, Python)
- **Pool mode:** Nhiều instance Camoufox, round-robin, mỗi instance một fingerprint riêng
- **Priority lease system:** `/acquire?priority=5&timeout=30` → đặt trước browser
- **Proxy pool:** Mỗi instance proxy riêng, blacklist khi fail
- Docker-ready, host network mode cho dynamic WS ports
- **Giải pháp production-ready cho multi-language + scale**

### 1.3 Chromium / CDP Engine Options

| Engine | Giao thức | Stealth | Ghi chú |
|---|---|---|---|
| **Chromium vanilla** | CDP (`connectOverCDP`) | ❌ Dễ bị phát hiện | `navigator.webdriver`, CDP exposure |
| **undetected-chromedriver** | CDP (Selenium) | ⚠️ JS-level patch | Dễ bị bypass, cần maintenance |
| **Patchright** | Playwright + patches | ⚠️ JS-level | Fragile |
| **Camoufox (Firefox)** | Juggler | ✅ C++ level | Chủ đề chính của tài liệu này |

**Tại sao Camoufox chọn Firefox thay vì Chromium?**
1. Chrome đóng, Chromium thiếu feature → anti-bot dễ phát hiện Chromium
2. CDP là mục tiêu phổ biến cho bot detection
3. Juggler hoạt động ở tầng thấp hơn CDP, khó rò rỉ hơn
4. Firefox có nhiều research về fingerprinting resistance

### 1.4 Container / Headless Linux

| Yếu tố | Khuyến nghị |
|---|---|
| Docker image | Có sẵn (Camoufox Connector, camofox-browser) |
| Shared memory | `--shm-size=2gb` (tối thiểu) |
| Headless mode | `headless=True` (native FF) hoặc `"virtual"` (Xvfb fallback) |
| Pool mode network | `--network host` bắt buộc trên Linux (dynamic WS ports) |
| Cache volume | Volume riêng cho Camoufox binaries (~300MB) |
| Resource tối ưu | Lazy browser launch + idle shutdown (40MB idle, ~550MB active) |

---

## Phần 2: Kiến trúc Đề xuất — Dual-Engine Design (Phased)

### 2.1 Triết lý thiết kế

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Interface (API)                      │
│   Profile Manager | Session Manager | Job Queue | Snapshot   │
├──────────────────────┬──────────────────────────────────────┤
│   Engine Layer        │                                      │
│   ┌────────────────┐  │  ┌────────────────────────────────┐  │
│   │  Engine A      │  │  │  Engine B (Vision)            │  │
│   │  (Camoufox/    │  │  │  (Chromium CDP)               │  │
│   │   Firefox/     │  │  │  Cho site cần Chromium-        │  │
│   │   Juggler)     │  │  │  specific rendering, hoặc      │  │
│   │   Stealth ưu   │  │  │  fallback khi Camoufox fail    │  │
│   │   tiên         │  │  │                                 │  │
│   └────────────────┘  │  └────────────────────────────────┘  │
├──────────────────────┴──────────────────────────────────────┤
│                    Cross-platform Runtime                     │
│         Windows (Win32) ─── Docker ─── Linux (headless)      │
└─────────────────────────────────────────────────────────────┘
```

**Lý do dual-engine:**
- Camoufox (Juggler) **tối ưu cho stealth** — chống Cloudflare, DataDome, Turnstile
- Chromium (CDP) **tối ưu cho Vision** — CDP có screenshot/recordVideo mạnh hơn, MCP/Playwright MCP tooling rộng hơn
- Chromium fallback khi Camoufox gặp vấn đề tương thích (maintenance gap 2025-2026)
- Một số site chỉ hoạt động đúng trên Chromium (WebKit/Safari testing, Chromium-only features)

### 2.2 Pha 1 — Foundation (Camoufox Engine)

#### Mục tiêu
- REST API quản lý profile + browser session
- Pool Camoufox instances
- Session persistence (cookies, localStorage)
- Element snapshot token-efficient

#### Kiến trúc

```
┌────────────────────────────────────────────────────┐
│               Profile Browser API                    │
│  GET/POST /profiles — CRUD profile config           │
│  POST /sessions — tạo session từ profile            │
│  GET  /tabs/:id/snapshot — snapshot accessibility   │
│  POST /tabs/:id/click — click theo element ref      │
│  POST /tabs/:id/type — gõ text                      │
│  GET  /tabs/:id/screenshot — screenshot             │
│  DELETE /sessions/:userId — đóng session            │
├────────────────────────────────────────────────────┤
│              Camoufox Pool Manager                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Camoufox │  │ Camoufox │  │ Camoufox │  ...      │
│  │ Inst 1   │  │ Inst 2   │  │ Inst N   │          │
│  │ WS :9222 │  │ WS :9223 │  │ WS :922X │          │
│  │ FP:A     │  │ FP:B     │  │ FP:N     │          │
│  └──────────┘  └──────────┘  └──────────┘          │
├────────────────────────────────────────────────────┤
│              Profile Storage Layer                    │
│  ~/.profiles/<hashed-userId>/storage_state.json     │
│  SQLite: profile config, proxy pool, rate limits     │
└────────────────────────────────────────────────────┘
```

#### API Model đề xuất

| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/profiles` | Tạo profile mới (os, screen, proxy, fingerprint preset) |
| `GET` | `/profiles` | Danh sách profiles |
| `GET` | `/profiles/:id` | Chi tiết profile |
| `PUT` | `/profiles/:id` | Cập nhật profile |
| `DELETE` | `/profiles/:id` | Xóa profile |
| `POST` | `/sessions` | Tạo session từ profile → trả về sessionId, tabId |
| `GET` | `/sessions/:userId` | Danh sách sessions của user |
| `DELETE` | `/sessions/:userId` | Đóng tất cả tabs + session |
| `GET` | `/tabs/:tabId/snapshot?includeScreenshot=true&offset=N` | Snapshot accessibility + element refs |
| `POST` | `/tabs/:tabId/click` | Click element theo ref hoặc selector |
| `POST` | `/tabs/:tabId/type` | Gõ text |
| `POST` | `/tabs/:tabId/navigate` | Điều hướng (URL hoặc search macro) |
| `GET` | `/tabs/:tabId/screenshot` | Chụp ảnh màn hình |
| `POST` | `/sessions/:userId/cookies` | Import cookies |
| `GET` | `/health` | Health check |
| `GET` | `/stats` | Pool statistics |

#### Job Model (cho Agent)

```
Agent gửi job request:
{
  "profileId": "prof_abc123",
  "actions": [
    {"type": "navigate", "url": "https://example.com"},
    {"type": "wait", "ms": 2000},
    {"type": "snapshot", "includeScreenshot": true},
    {"type": "click", "ref": "e1"},
    {"type": "type", "ref": "e2", "text": "search query"},
    {"type": "extract", "schema": {...}}
  ]
}

Response:
{
  "jobId": "job_xyz789",
  "status": "completed",
  "results": [
    {"action": "navigate", "status": "ok", "url": "https://..."},
    {"action": "snapshot", "output": "accessibility tree..."},
    ...
  ],
  "tokenUsage": {"snapshot": 450, "screenshot": null}
}
```

### 2.3 Pha 2 — Dual-Engine (Camoufox + Chromium CDP)

#### Kiến trúc mở rộng

```
┌────────────────────────────────────────────────────────────┐
│                   Engine Router                               │
│  Dựa trên profile config hoặc auto-detect site requirements │
│  Rule: use Chromium nếu profile.engine = "chromium"         │
│        hoặc Camoufox fail > N lần → fallback                │
├─────────────────────┬──────────────────────────────────────┤
│   Engine A          │   Engine B                             │
│   Camoufox Pool     │   Chromium CDP (connectOverCDP)       │
│   ┌──────────────┐  │   ┌──────────────────────────────┐    │
│   │ Juggler WS   │  │   │ CDP WS (--remote-debugging)  │    │
│   │ Python native│  │   │ Python/Node.js client        │    │
│   │ + connector  │  │   │ + undetected-chromedriver    │    │
│   └──────────────┘  │   └──────────────────────────────┘    │
├─────────────────────┴──────────────────────────────────────┤
│                    Profile Abstraction Layer                  │
│  Storage state format unified giữa 2 engines                 │
│  Cookies + localStorage + session storage                    │
└────────────────────────────────────────────────────────────┘
```

#### So sánh Engine cho quyết định routing

| Tiêu chí | Camoufox (Juggler) | Chromium (CDP) |
|---|---|---|
| **Stealth** | ✅✅✅ C++ level, sandboxed | ❌ Dễ phát hiện (navigator.webdriver, CDP) |
| **Context persistence qua connect** | ❌ `browser.contexts` rỗng | ✅ `connectOverCDP` giữ context |
| **Profile isolation** | ⚠️ persistent_context limited | ✅ User Data Dir riêng |
| **Screenshot/recordVideo** | ⚠️ Chụp được, không recordVideo | ✅✅ CDP có nhiều tool |
| **MCP / AI Agent tooling** | ⚠️ MCP server mới, 21 tools | ✅✅ Hệ sinh thái rộng (Browserbase, Playwright MCP) |
| **Docker footprint** | ✅ ~200MB (gọn nhẹ) | ⚠️ ~800MB+ (Chromium) |
| **Tương thích site** | ⚠️ Có site Firefox-specific issues | ✅ Đa số site tối ưu cho Chrome |
| **Maintenance** | ⚠️ Cần theo dõi Camoufox updates | ✅ Chromium update đều đặn |

### 2.4 Container / Deployment Strategy

```yaml
# docker-compose.yml — Production
version: '3.8'
services:
  profile-browser-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENGINE_MODE=dual        # 'camoufox' | 'chromium' | 'dual'
      - CAMOUFOX_POOL_SIZE=5
      - CHROMIUM_POOL_SIZE=2
      - PROXY_POOL=...
    volumes:
      - profiles:/app/profiles
      - camoufox-cache:/root/.cache/camoufox
    shm_size: 4gb
    network_mode: host           # Cần cho dynamic WS ports
    restart: unless-stopped

  # Optional: Chromium sidecar nếu cần isolation riêng
  chromium-pool:
    image: browserless/chrome
    environment:
      - CONNECTION_TIMEOUT=60000
      - MAX_CONCURRENT_SESSIONS=5
    ports:
      - "3000:3000"

volumes:
  profiles:
  camoufox-cache:
```

---

## Phần 3: Chiến lược Kiểm thử

### 3.1 Unit Tests (Layer 1)

| Module | Test coverage | Công cụ |
|---|---|---|
| Profile CRUD | validate schema, boundary | pytest + pydantic |
| Session lifecycle | create/close/timeout | pytest-asyncio |
| Pool manager | acquire/release/priority | pytest + asyncio |
| Proxy pool | round-robin, blacklist, rotate | pytest |
| Snapshot parser | parse tree → element refs | pytest |
| API auth | bearer token, rate limit | httpx |

### 3.2 Integration Tests (Layer 2)

| Kịch bản | Mô tả |
|---|---|
| Launch Camoufox instance via API | POST /sessions → verify WS connected |
| Snapshot real page | GET /tabs/:id/snapshot → verify tree |
| Click + type chain | POST click → POST type → verify DOM change |
| Session persistence | Tạo session → add cookies → close → reopen → verify cookies tồn tại |
| Proxy assignment | Mỗi instance proxy riêng → verify IP |

### 3.3 Engine Comparison Tests (Layer 3)

| Test | Mục tiêu |
|---|---|
| **Stealth benchmark** | So sánh Camoufox vs Chromium trên: `https://bot.sannysoft.com`, `https://fingerprintjs.com`, `https://abrahamjuliot.github.io/creepjs` |
| **Turnstile challenge** | Camoufox vượt Cloudflare Turnstile? Tỉ lệ thành công |
| **DataDome / Imperva** | Camoufox có pass? |
| **Site compatibility matrix** | 20 site phổ biến (Google, Amazon, LinkedIn, Reddit, etc.) — engine nào pass? |
| **Memory/footprint** | Camoufox idle 40MB vs Chromium idle ~200MB |

### 3.4 E2E Agent Workflow Tests

```
Agent workflow mẫu:
1. POST /profiles (create profile Windows 11, proxy USA)
2. POST /sessions (session từ profile)
3. GET /tabs/:id/snapshot (trang login)
4. POST /tabs/:id/click ref="username-field"
5. POST /tabs/:id/type text="user@example.com"
6. POST /tabs/:id/click ref="password-field"
7. POST /tabs/:id/type text="password"
8. POST /tabs/:id/click ref="login-button"
9. GET /tabs/:id/screenshot (verify logged in)
10. DELETE /sessions/:userId (cleanup)
```

### 3.5 CI/CD Pipeline

```yaml
# GitHub Actions
jobs:
  test:
    strategy:
      matrix:
        engine: [camoufox, chromium, dual]
    steps:
      - checkout
      - docker compose up -d
      - pytest tests/unit/
      - pytest tests/integration/
      - pytest tests/engine/ --engine=${{ matrix.engine }}
      - pytest tests/e2e/
```

---

## Phần 4: Rủi ro và Giảm thiểu

| Rủi ro | Mức | Giải pháp |
|---|---|---|
| **Camoufox maintenance gap** (2025-2026) | 🔴 Cao | Engine B (Chromium) fallback; theo dõi Clover Labs updates |
| **Remote server experimental** | 🔴 Cao | Dùng Camoufox Connector (production-proven); pool mode thay vì single server |
| **Juggler context loss khi reconnect** | 🟡 Trung bình | Workaround: dùng Playwright BrowserContext riêng, lưu storage_state, restore sau |
| **Firefox site incompatibility** | 🟡 Trung bình | Engine routing: Chromium cho site có vấn đề |
| **Dynamic WS ports trong Docker** | 🟡 Trung bình | `network_mode: host` hoặc Port mapping fixed với single mode |
| **Cold start latency (~300MB download)** | 🟢 Thấp | Pre-cache volume, pre-download trong Dockerfile |
| **Fingerprint inconsistency** | 🟢 Thấp | Theo dõi Camoufox changelog, cập nhật thường xuyên |
| **Chromium detection upgrade** | 🟢 Thấp | Camoufox là primary, Chromium chỉ là fallback tạm thời |

### Rủi ro lớn nhất: Camoufox Remote Server là Experimental

**Phân tích:**
- Camoufox docs ghi rõ "experimental — hacky workaround to undocumented Playwright methods"
- Issue #209 vẫn mở, không có giải pháp chính thức cho persistent context qua WS
- `browser.contexts` trả về rỗng sau connect → không giữ được tabs/sessions

**Giải pháp:**
1. **Pha 1:** Dùng Camoufox **native Python API** (`Camoufox()`) cho single-process agent, không dùng remote server
2. **Pha 1 mở rộng:** Dùng Camoufox Connector cho Pool mode (production-proven, 68 unit tests)
3. **Pha 2:** Thêm Chromium CDP engine cho connectOverCDP — context persistence hoạt động native
4. **Hybrid:** Agent ngắn hạn (1-5 actions) → Camoufox native. Agent dài hạn (multi-session) → Chromium CDP với profile persistence

---

## Phần 5: Tóm tắt Khuyến nghị

### Kiến trúc Tổng thể

```
PHA 1 (Foundation)                  PHA 2 (Dual-Engine)
┌──────────────────┐               ┌──────────────────────┐
│  Camoufox Native │ ───→          │  Camoufox Native     │
│  (Python)        │               │  + Chromium CDP      │
│  + Pool Manager  │               │  + Engine Router     │
│  + REST API      │               │  + Profile Abstraction│
│  + Profile Store │               │  + Unified Snapshot  │
│  + Session Cache │               │  + Job Queue         │
└──────────────────┘               └──────────────────────┘
      3-4 weeks                          6-8 weeks
```

### Công nghệ chính

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| **Primary Engine** | Camoufox (Python) | Stealth C++ level, Juggler sandboxed |
| **Secondary Engine** | Chromium CDP | Context persistence, Vision, fallback |
| **API Framework** | FastAPI / Node.js Express | FastAPI (nếu Python-first), Express (nếu inspired from camofox-browser) |
| **Container** | Docker + Compose | Cross-platform, reproducible |
| **Profile Storage** | JSON + SQLite | Đơn giản, đủ cho agent workloads |
| **Snapshot Format** | Accessibility Tree | ~90% nhỏ hơn HTML, token-efficient |
| **Protocol Bridge** | Camoufox Connector | Pool mode, multi-language, priority queue |

### Tham khảo

- [Camoufox Documentation](https://camoufox.com/)
- [Camoufox Remote Server](https://camoufox.com/python/remote-server/)
- [Camoufox Connector (pim97)](https://github.com/pim97/camoufox-connector)
- [camofox-browser (jo-inc)](https://github.com/jo-inc/camofox-browser)
- [Juggler Protocol](https://github.com/puppeteer/juggler)
- [Issue #209 — Persistent Browser Sessions](https://github.com/daijro/camoufox/issues/209)
