# Nghiên cứu Kiến trúc Browser Agent-First cho Phantom

> Tài liệu tổng hợp các mẫu kiến trúc, API, và bài học từ các dự án mã nguồn mở hàng đầu.
> Biên soạn: 2026-07-19

---

## Mục lục

1. [Tổng quan hệ sinh thái](#1-tổng-quan-hệ-sinh-thái)
2. [Browserless — Node.js Docker Browser Pool](#2-browserless--nodejs-docker-browser-pool)
3. [Steel Browser — Open-Source Browser API cho AI Agents](#3-steel-browser--open-source-browser-api-cho-ai-agents)
4. [Browser Use — Python CDP-Native AI Agent](#4-browser-use--python-cdp-native-ai-agent)
5. [BrowseForge — Anti-Detect Workspace Đa Runtime](#5-browseforge--anti-detect-workspace-đa-runtime)
6. [Camoufox — Firefox Fork Chống Phát Hiện](#6-camoufox--firefox-fork-chống-phát-hiện)
7. [Stagehand v3 — CDP-Native SDK cho Browser Agents](#7-stagehand-v3--cdp-native-sdk-cho-browser-agents)
8. [Playwright MCP — Microsoft](#8-playwright-mcp--microsoft)
9. [So sánh Camoufox vs Chromium CDP](#9-so-sánh-camoufox-vs-chromium-cdp-cho-phantom)
10. [Mẫu Kiến trúc Đề xuất cho Phantom](#10-mẫu-kiến-trúc-đề-xuất-cho-phantom)

---

## 1. Tổng quan hệ sinh thái

Thị trường browser infrastructure cho AI agents đang phân làm 3 tầng:

| Tầng | Ví dụ | Vai trò |
|------|-------|---------|
| **Managed Cloud** | Browserbase ($300M), Steel.dev, Bright Data | Hạ tầng browser đám mây, fingerprint, CAPTCHA |
| **Framework AI-Native** | Stagehand, Browser Use, Playwright MCP | Lớp abstraction cho LLM tương tác browser |
| **Giao thức** | CDP, WebDriver BiDi, WebMCP, MCP | Chuẩn kết nối browser-agent |

**Nguồn tham khảo:**
- https://agentmarketcap.ai/blog/2026/04/09/browser-use-agent-infrastructure-browserbase-stagehand-playwright-mcp
- https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape/

---

## 2. Browserless — Node.js Docker Browser Pool

- **GitHub:** https://github.com/browserless/browserless ⭐ 13.5k
- **Docs:** https://docs.browserless.io/
- **Ngôn ngữ:** Node.js/TypeScript
- **License:** SSPL (phiên bản OSS miễn phí)

### Kiến trúc

```
Browserless HTTP Service (:3000)
  ├── REST APIs (/chromium/screenshot, /pdf, /scrape, /content, /function)
  ├── WebSocket (/chromium/playwright, root cho Puppeteer CDP)
  ├── Management (/pressure, /sessions, /metrics, /config)
  ├── MCP Server (https://mcp.browserless.io/mcp)
  └── Debugger UI (/)
```

### Pool & Concurrency Pattern

```dockerfile
# Docker env vars cho pool management
CONCURRENT=10    # Tối đa browser sessions đồng thời
QUEUED=10        # Hàng đợi khi đầy concurrent
TIMEOUT=30000    # Session timeout (ms)
HEALTH=true      # Pre-request health checks
MAX_CPU_PERCENT=80
MAX_MEMORY_PERCENT=80
```

Browserless hoạt động như một **proxy browser pool**: mỗi request đến kết nối WebSocket với Chrome/CDP qua Puppeteer/Playwright, chạy trong container, tự động quản lý vòng đời.

### Session Lease & TTL Pattern

Sử dụng CDP command tùy chỉnh `Browserless.reconnect`:

```js
// Gọi trước khi disconnect để giữ browser sống
const { browserWSEndpoint } = await cdp.send("Browserless.reconnect", {
  timeout: 30000, // Browser sống tối đa 30s chờ reconnect
});
await browser.disconnect(); // Detach local, browser vẫn chạy trên server

// Reconnect sau đó:
const browser = await puppeteer.connect({
  browserWSEndpoint: `${browserWSEndpoint}?token=${TOKEN}`
});
```

Giới hạn TTL theo plan: Free 10s → Scale 5 phút → Enterprise custom.

### MCP Integration

Browserless cung cấp MCP server hosted + local:

- **Stateful tool:** `browserless_agent` — duy trì session browser qua nhiều turn
- **Stateless tools:** `browserless_smartscraper`, `browserless_function`, `browserless_search`, `browserless_crawl`, etc.

**Bài học cho Phantom:**
- Dùng env vars để cấu hình pool (CONCURRENT, QUEUED, TIMEOUT) — đơn giản, dễ vận hành
- CDP custom commands (`Browserless.reconnect`) cho session lease
- MCP server như một mặt bằng tích hợp agents
- Health checks trước khi nhận request (back-pressure)

---

## 3. Steel Browser — Open-Source Browser API cho AI Agents

- **GitHub:** https://github.com/steel-dev/steel-browser ⭐ 7.3k
- **Web:** https://steel.dev/
- **Docs:** https://docs.steel.dev/

### Kiến trúc Sessions API

Steel định nghĩa browser session như first-class resource:

```
POST /v1/sessions         → Tạo session, trả về { id, wsEndpoint, status }
GET  /v1/sessions/{id}    → Lấy trạng thái session
POST /v1/sessions/{id}/release → Giải phóng session
```

Mỗi session:
- Là một browser instance riêng biệt
- Chạy cloud, có CDP endpoint qua WebSocket
- TTL lên đến 24h
- Hỗ trợ context reuse (cookies, localStorage)

### Features chính

| Feature | Mô tả |
|---------|-------|
| **Proxy fingerprinting** | Chống bot detection |
| **CAPTCHA solving** | Tự động xử lý CAPTCHA |
| **Session viewer** | Replay và debug session |
| **Auto sign-in** | Quản lý credential an toàn |
| **Context management** | Lưu/inject cookies, localStorage |

### SDK Pattern

```python
from steel import Steel

client = Steel()
session = client.sessions.create()
# session.ws_endpoint -> ws://... để kết nối Puppeteer/Playwright
```

Và 1-line change để chạy Puppeteer/Playwright trên Steel cloud thay vì local.

**Bài học cho Phantom:**
- RESTful session CRUD làm API chính
- WebSocket endpoint riêng cho từng session
- Context reuse qua cookies/storage injection
- Session viewer/video replay cho observability

---

## 4. Browser Use — Python CDP-Native AI Agent

- **GitHub:** https://github.com/browser-use/browser-use ⭐ 78k
- **Architecture analysis:** https://martianlee.github.io/posts/2026-06-30-browser-use-architecture
- **Ngôn ngữ:** Python
- **Browser control:** CDP (cdp-use) — **KHÔNG dùng Playwright**

### Kiến trúc Chi tiết

```
Agent.run()
  └── step() / multi_act()
       ├── message_manager → Xây prompt (system prompt + page state + history)
       ├── DOM serializer → Clickable elements indexed list
       │    ├── dom/service.py: DOM tree extraction (EnhancedDOMTreeNode)
       │    ├── dom/serializer/clickable_elements.py: Interactivity scoring
       │    ├── dom/serializer/paint_order.py: Z-order filtering
       │    └── dom/serializer/serializer.py: Indexed serialization
       ├── LLM (16 providers) → ActionModel (structured output)
       ├── tools/registry → Action vocabulary (click, type, scroll, extract, done)
       └── BrowserSession (CDP) + event bus + 14 watchdogs
            ├── crash_watchdog     → Crash recovery
            ├── popups_watchdog    → Xử lý popup tự động
            ├── downloads_watchdog → Quản lý download
            ├── captcha_watchdog   → Phát hiện CAPTCHA
            ├── security_watchdog  → Security events
            ├── dom_watchdog       → DOM updates
            └── screenshot_watchdog → Screenshot tự động
```

### CDP-Native Design

Browser Use bỏ Playwright hoàn toàn, gọi CDP trực tiếp qua `cdp-use`:

- CDP calls: 26 files
- Playwright: ~1 file (optional)

**Event bus (bubus):** Stream các sự kiện browser (navigation, downloads, popups, crashes) — phản ứng theo sự kiện thay vì imperative.

### DOM Serialization Pattern (Quan trọng nhất)

```
1. DOM tree extraction (CDP DOMSnapshot)
2. is_interactive(node) → Score-based heuristic cho nút clickable/typable
3. paint_order computation → Loại bỏ element bị che khuất
4. Indexing + serialization → [5]<button>Submit</button>

LLM nhận danh sách đánh số, không cần viết selector:
→ "Click element 5" thay vì await page.click('button.submit')
```

### MCP Integration

Browser Use chạy như MCP server, cho phép agent khác (coding agent, etc.) gọi browser capability.

### Bài học cho Phantom

| Pattern | Áp dụng |
|---------|---------|
| **DOM serialization** thay vì raw HTML cho LLM | Pre-chew page → interactive elements indexed list |
| **Event bus + watchdogs** | Crash recovery, popup handling, CAPTCHA detection tự động |
| **CDP-native** | Bỏ Playwright overhead, kiểm soát mịn hơn |
| **Action registry** | Action vocabulary cố định → structured output thay vì code gen |
| **Per-model prompts** | System prompt riêng cho từng class model (flash, no-thinking, etc.) |

---

## 5. BrowseForge — Anti-Detect Workspace Đa Runtime

- **GitHub:** https://github.com/nczz/BrowseForge ⭐ 31
- **API Reference:** https://github.com/nczz/BrowseForge/blob/main/API.md
- **Dual-Browser Architecture:** https://github.com/nczz/BrowseForge/blob/main/docs/dual-browser-architecture.md
- **Ngôn ngữ:** Go (83%) + HTML/JS

### Kiến trúc Tổng thể

```
BrowseForge HTTP Service (:19280)
  ├── REST API (/api)
  │    ├── /api/profiles → CRUD profile (camoufox, cloakbrowser)
  │    ├── /api/sessions → Browser session lifecycle
  │    ├── /api/sessions/{id}/{navigate,click,type,eval,screenshot,content}
  │    ├── /api/groups → Group proxy policy
  │    ├── /api/backup → Full backup ZIP
  │    └── /api/workflow/run → YAML workflow execution
  ├── MCP Streamable HTTP (/mcp)
  │    ├── list_profiles, create_profile, open_browser, close_browser
  │    ├── web_search, web_explore, web_extract
  │    ├── form_fill, select_option, check, press_key
  │    ├── get_cookies, set_cookies
  │    ├── list_downloads, read_download, delete_download
  │    ├── screenshot (lưu artifact trong profile)
  │    ├── wait_for, get_page_state
  │    └── doctor_profile, run_workflow
  ├── Web Dashboard (/) — Giao diện quản lý profile
  └── Playwright WebSocket (/api/playwright/ws/{session_id})
```

### Multi-Runtime Pattern

BrowseForge hỗ trợ 3 runtime engines, config qua `config.json`:

```json
{
  "default_runtime_id": "camoufox",
  "runtimes": {
    "camoufox": {
      "enabled": true,
      "family": "firefox",
      "binary_path": "browsers/camoufox/..."
    },
    "cloakbrowser": {
      "enabled": true,
      "family": "chromium",
      "binary_path": "browsers/cloakbrowser/..."
    },
    "browseforge-chromium": {
      "enabled": true,
      "family": "chromium",
      "binary_path": "browsers/browseforge-chromium/chrome"
    }
  }
}
```

Mỗi profile gắn với một runtime_id. Profile isolation: mỗi profile có process browser riêng, thư mục dữ liệu riêng.

### Fingerprint Pool

```
Config: fingerprint_dir = "data/"
Mỗi fingerprint JSON bao gồm: navigator, screen, window, font, canvas seed,
timezone, WebRTC, WebGL (all-or-nothing policy cho WebGL)
```

### Profile Groups & Proxy Policy

```json
{
  "proxy_mode": "default",    // Profile proxy → Group proxy → No proxy
  "proxy_mode": "enforced",   // Group proxy → Profile proxy → No proxy
  "proxy": {
    "type": "socks5",
    "host": "proxy.example.com",
    "port": 1080,
    "region": "us-ny"  // Label địa lý, ko chứa IP thật
  }
}
```

### Agent Web Sessions Pattern (MCP)

```
Profile → Browser instance (browser.Manager)
  └── SessionPool → connectedBrowser.NewPage()
       ├── Session_id pins calls to same page
       ├── Idle TTL: 5 phút
       ├── GC sweep: 1 phút
       └── Max sessions per profile: 10
```

### Playwright Connect

```js
// External Playwright attach vào session đang chạy
const browser = await firefox.connect(
  'ws://YOUR_SERVER:19280/api/playwright/ws/sess_prof_xxx',
  { headers: { Authorization: 'Bearer YOUR_TOKEN' } }
);
```

### YAML Workflows

```yaml
name: Multi-account login
steps:
  - name: Create profile
    action: create_profile
    params: { name: "FB Account", runtime_id: camoufox, var: p1 }
  - name: Open browser
    action: open_browser
    profile_id: $p1
  - name: Navigate
    action: navigate
    profile_id: $p1
    params: { url: "https://facebook.com" }
```

### Bài học cho Phantom

| Pattern | Chi tiết |
|---------|----------|
| **Profile CRUD + backup/restore** | Mỗi profile là thư mục riêng, export được ZIP |
| **Group proxy policy** | Proxy inheritance: profile → group → none |
| **Multi-runtime abstraction** | Runtime provider contract thống nhất REST/MCP/Playwright |
| **MCP Streamable HTTP** | MCP trên cùng port chính, có Bearer auth |
| **Fingerprint pool** | JSON fingerprint, auto-assign khi tạo profile, timezone/locale-aware |
| **Session GC** | TTL + GC sweep cho idle agent sessions |
| **Artifact saving** | Screenshot lưu vào profile artifacts directory |
| **Workflow engine** | YAML-based multi-step automation |

---

## 6. Camoufox — Firefox Fork Chống Phát Hiện

- **GitHub:** https://github.com/daijro/camoufox ⭐ 10.3k
- **Web:** https://camoufox.com/
- **Base:** Firefox (fork C++)

### Kiến trúc Kỹ thuật

```
Camoufox (Firefox fork)
  ├── C++ level patching (not JS injection)
  │    ├── navigator properties (device, OS, hardware, browser)
  │    ├── WebGL parameters, extensions, context attributes
  │    ├── Screen, window, viewport properties
  │    ├── Geolocation, timezone, locale, Intl spoofing
  │    ├── WebRTC IP spoofing (protocol level)
  │    ├── Font spoofing & canvas fingerprinting
  │    └── AudioContext parameters
  ├── Playwright integration (Juggler protocol)
  │    └── Page Agent runs in sandboxed world → khó phát hiện
  ├── BrowserForge fingerprint rotation
  │    └── Real-world device distribution matching
  └── <200MB footprint, headless-first
```

### Tại sao Firefox mà không phải Chromium?

| Lý do | Giải thích |
|-------|------------|
| Chrome ≠ Chromium | Anti-bot có thể phát hiện Chromium không phải Chrome vì thiếu feature closed-source |
| CDP là mục tiêu phổ biến | CDP được biết đến rộng rãi → dễ bị phát hiện hơn |
| Juggler level thấp hơn CDP | Juggler operate ở level thấp hơn CDP → ít JS leaks |
| Fingerprint rotation tốt hơn | Firefox có nhiều research về fingerprinting resistance hơn Chromium |

### Detection Score

- 0% detection trên CreepJS và BrowserScan (v146.0.1-beta.25)
- Camoufox > Nodriver > undetected-chromedriver về stealth

### Build & Deploy

```
camoufox set for channel selectors (official/stable, official/prerelease)
camoufox set browser <version>  # Version selectors

# PyPI package: camoufox
# Tự động download và cập nhật fingerprint injection
```

**Bài học cho Phantom:**
- Firefox patching ở C++ level là khả thi cho anti-detection
- Juggler protocol an toàn hơn CDP cho automation stealth
- <200MB footprint → scale tốt hơn Chrome
- Cần kết hợp fingerprint rotation (BrowserForge) để realistic identity

---

## 7. Stagehand v3 — CDP-Native SDK cho Browser Agents

- **GitHub:** https://github.com/browserbase/stagehand ⭐ 50k+
- **Web:** https://www.stagehand.dev/
- **Kết hợp:** https://www.browserbase.com/

### API Primitives

```typescript
// 4 primitives chính:
await page.act("Fill in the email field");      // Natural language action
await page.extract("Get all product prices");     // Structured extraction
await page.observe("Find the login button");      // Observe elements
await page.agent("Book a flight to Paris");       // Autonomous agent
```

### v3 Architecture Shift (2026)

Stagehand v3 bỏ Playwright, rebuild native trên CDP → **44% reduction in round-trip time**:

- Auto-caching elements → không gọi LLM cho repeated actions
- Self-healing: phát hiện website thay đổi, re-invoke AI only when needed
- CDP-native: DOM extraction, accessibility tree, network intercept

### Browserbase Cloud Integration

Browserbase cung cấp:
- Serverless browser fleet (milliseconds launch)
- Session management
- Fingerprint management
- CAPTCHA solving
- Session replay/observability

---

## 8. Playwright MCP — Microsoft

- **GitHub:** https://github.com/microsoft/playwright-mcp
- **Docs:** https://playwright.dev/docs/getting-started-mcp

### Kiến trúc

Playwright MCP server expose browser control qua **accessibility tree snapshots** (không screenshots):

```
Page snapshot:
├── heading "todos" [level=1]
├── textbox "What needs to be done?" [ref=e5]
├── listitem:
│   ├── checkbox "Toggle Todo" [ref=e10]
│   └── text: "Buy groceries"

LLM dùng ref=e5 để type, ref=e10 để click
```

### Profile Modes

| Mode | Mô tả |
|------|-------|
| **Persistent (default)** | Cookies/state preserved giữa sessions. Profile stored trong cache directory |
| **Isolated** | Mỗi session fresh (--isolated). Có thể load initial state qua --storage-state |
| **Extension** | Kết nối tới browser tabs hiện tại qua Playwright Extension |

### Configuration

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--browser=firefox",    // chrome, firefox, webkit, msedge
        "--headless",           // hoặc headed (default)
        "--user-data-dir=/path/to/profile",
        "--isolated"            // Ephemeral mode
      ]
    }
  }
}
```

---

## 9. So sánh Camoufox vs Chromium CDP cho Phantom

| Tiêu chí | Camoufox (Firefox/Juggler) | Chromium CDP |
|----------|---------------------------|--------------|
| **Anti-detection** | ✅ Xuất sắc (C++ patches, 0% CreepJS) | ⚠️ Tốt (có stealth patches nhưng CDP dễ detect) |
| **Automation** | ⚠️ Playwright Juggler (hạn chế hơn CDP) | ✅ CDP đầy đủ (DOM, Network, Profiling, etc.) |
| **Footprint** | ✅ ~200MB | ⚠️ ~800MB+ |
| **Cross-browser** | ❌ Firefox only | ⚠️ Chromium ecosystem (Edge, Brave, etc.) |
| **Caching** | ⚠️ Profile riêng biệt | ✅ User Data Directory pattern |
| **Ecosystem** | ⚠️ Ít tool hơn | ✅ Browserless, Puppeteer, Playwright, Stagehand |
| **Container** | ✅ Chạy Docker được | ✅ Chạy Docker được (cần --no-sandbox) |
| **Profile isolation** | ✅ Process riêng/profile | ✅ User Data Dir riêng/profile |
| **MCP support** | ⚠️ Qua BrowseForge | ✅ Nhiều (browser-use, Stagehand, Playwright MCP) |
| **LLM DOM parsing** | ⚠️ Juggler DOM ít phổ biến | ✅ Accessibility tree, CDP DOMSnapshot |
| **Cost** | Miễn phí OSS | Miễn phí OSS |

### Khuyến nghị cho Phantom

**Giai đoạn Windows-first:**
- **Khởi đầu với Chromium CDP** — ecosystem lớn, CDP feature đầy đủ, dễ tích hợp với Browserless/Steel patterns
- **Thêm Camoufox như runtime tùy chọn** — Cho use case cần anti-detection tối đa

**Kiến trúc Dual-Runtime (học từ BrowseForge):**
```
Phantom Core Service
  ├── Runtime Provider Interface
  │    ├── chromium_cdp_provider.go → Profile, Session, CDP
  │    └── firefox_camoufox_provider.go → Profile, Session, Juggler
  ├── Profile Store (filesystem-based)
  ├── REST API
  ├── MCP Server
  └── Playwright Connect
```

Khi nào dùng Camoufox:
- Anti-detection là ưu tiên số 1
- Need Firefox-level fingerprint stealth
- Scale nhỏ (<100 concurrent)

Khi nào dùng Chromium CDP:
- Cần CDP đầy đủ (DOM extraction, network, debugging)
- Tích hợp với ecosystem agents (browser-use, Stagehand)
- Scale lớn

---

## 10. Mẫu Kiến trúc Đề xuất cho Phantom

### 10.1. Profile Management (học từ BrowseForge)

```
profiles/
  ├── prof_{uuid1}/
  │    ├── profile.json        # Metadata: name, runtime_id, proxy, fingerprint, group, tags
  │    ├── browser-data/        # Firefox profile dir / Chromium User Data
  │    ├── artifacts/           # Screenshots, HAR files, downloads
  │    └── cookies.json         # Exported cookies
  └── prof_{uuid2}/...
```

**API pattern:**
```
POST /api/profiles       → { name, runtime_id, proxy, fingerprint, group, tags }
GET  /api/profiles       → List (filter by group, tag, runtime)
GET  /api/profiles/{id}  → Detail
PUT  /api/profiles/{id}  → Update metadata
DELETE /api/profiles/{id} → Xóa
POST /api/profiles/{id}/duplicate → Clone với fingerprint mới
POST /api/profiles/{id}/export    → ZIP export
POST /api/profiles/import         → ZIP import
```

### 10.2. Session Lifecycle & Leases

```
POST /api/sessions → Start session (profile_id, ttl?)
  → Returns { session_id, ws_endpoint, runtime_id }
DELETE /api/sessions/{id} → Close
GET /api/sessions → List active

Session state machine:
  CREATED → STARTING → RUNNING → CLOSING → CLOSED
                  ↓ (error)
                 FAILED → CLOSED
```

**TTL/Idle timeout (học từ BrowseForge + Steel):**
- Session hard TTL: 24h (giống Steel)
- Idle timeout: 5 min (giống BrowseForge agent sessions)
- GC sweep: 1 min

**Idempotency key:**
```
Header: X-Idempotency-Key: <uuid>
→ POST /api/sessions với cùng key → trả về session hiện tại (nếu còn sống)
→ Giải pháp: kiểm tra key trong cache 5 phút
```

### 10.3. Browser Pool & Crash Recovery

**Pool architecture (học từ Browserless):**
```
Browser Pool Manager
  ├── Max concurrent: CONCURRENT (env)
  ├── Queue: QUEUED (env)
  ├── Per-session timeout: TIMEOUT (env)
  ├── Health checks: CPU, memory pressure
  └── Crash recovery:
       ├── Watchdog process (học từ browser-use)
       ├── Auto-restart on crash (max 3 lần)
       └── Session failed → agent callback/webhook
```

### 10.4. Event Streams & Artifacts

```json
// SSE stream cho session events:
GET /api/sessions/{id}/events
→ event: navigation_complete
  data: {"url": "...", "timestamp": "..."}
→ event: crash
  data: {"reason": "OOM", "recovered": true}
```

**Artifacts per session:**
```
sessions/{session_id}/
  ├── screenshots/
  ├── har/            # Network HAR files
  ├── downloads/
  └── console.log     # Browser console output
```

### 10.5. MCP Server Design

**Transport:**
- Streamable HTTP (chính) — reuse REST port
- stdio (optional) — cho local AI tools

**Tool categories:**
```
Profile tools: list_profiles, create_profile, delete_profile, update_profile
Session tools: open_browser, close_browser, navigate, click, type_text, screenshot
Page tools: get_content, evaluate, wait_for, get_page_state, form_fill
Network tools: get_cookies, set_cookies, get_har
Search tools: web_search, web_explore, web_extract (học từ BrowseForge)
Diagnostics: doctor_profile, list_sessions, gc_sessions
```

### 10.6. Container Isolation

**Production Docker:**
```dockerfile
# Học từ BrowseForge + Browserless
docker run -d --name phantom \
  -p 19280:19280 \
  -v ./profiles:/app/profiles \
  -v ./data:/app/data \
  -e CONCURRENT=10 \
  -e QUEUED=10 \
  -e TIMEOUT=300000 \
  --shm-size=2g \
  --restart unless-stopped \
  ghcr.io/phantom/phantom:latest
```

**K8S cho scale lớn:**
- Mỗi pod = 1 Phantom instance với browser concurrency limit
- PersistentVolumeClaim cho profiles/
- Service mesh cho gRPC/CDP traffic
- HPA dựa trên CPU/memory/session count

### 10.7. Tổng hợp các Pattern chính

| Pattern | Nguồn tham khảo | Áp dụng cho Phantom |
|---------|-----------------|---------------------|
| **Profile CRUD + backup/restore** | BrowseForge, Steel | Persistent profile store |
| **Session lease (TTL + idempotency)** | Browserless (reconnect), Steel (24h) | Session lifecycle API |
| **Event bus + watchdogs** | Browser Use (bubus + 14 watchdogs) | Crash recovery, popup/auto-CAPTCHA |
| **CDP-native control** | Browser Use, Stagehand v3 | Chromium runtime chính |
| **Multi-runtime abstraction** | BrowseForge (camoufox/cloakbrowser) | Plugable runtime provider |
| **DOM serialization cho LLM** | Browser Use (indexed clickable elements) | Pre-chew page cho agent |
| **MCP Streamable HTTP** | BrowseForge, Browserless, Playwright MCP | AI agent integration |
| **Fingerprint pool** | BrowseForge, Camoufox | Profile-based fingerprint |
| **Group proxy policy** | BrowseForge | Proxy inheritance hierarchy |
| **Accessibility tree snapshots** | Playwright MCP | Structured page state cho LLM |
| **Dual engine: Firefox + Chromium** | BrowseForge | Camoufox cho stealth, CDP cho feature |
| **Browser pool + concurrency** | Browserless (CONCURRENT/QUEUED) | Resource management |
| **YAML Workflows** | BrowseForge | Multi-step automation scripts |
| **Container isolation** | Browserless (Docker), BrowseForge | Production deployment |

---

## Danh sách URL Nguồn Chính

### Dự án mã nguồn mở
- **Browserless:** https://github.com/browserless/browserless — Docs: https://docs.browserless.io/
- **Steel Browser:** https://github.com/steel-dev/steel-browser — Docs: https://docs.steel.dev/ — Web: https://steel.dev/
- **Browser Use:** https://github.com/browser-use/browser-use — Docs: https://docs.browser-use.com/
- **BrowseForge:** https://github.com/nczz/BrowseForge — API: https://github.com/nczz/BrowseForge/blob/main/API.md
- **Camoufox:** https://github.com/daijro/camoufox — Web: https://camoufox.com/
- **Stagehand:** https://github.com/browserbase/stagehand — Web: https://www.stagehand.dev/
- **Playwright MCP:** https://github.com/microsoft/playwright-mcp — Docs: https://playwright.dev/docs/getting-started-mcp

### Phân tích kiến trúc
- **Browser Use Architecture:** https://martianlee.github.io/posts/2026-06-30-browser-use-architecture
- **BrowseForge Dual-Browser Architecture:** https://github.com/nczz/BrowseForge/blob/main/docs/dual-browser-architecture.md
- **Agent Infrastructure Race:** https://agentmarketcap.ai/blog/2026/04/09/browser-use-agent-infrastructure-browserbase-stagehand-playwright-mcp
- **Browser Automation Landscape 2026:** https://zylos.ai/research/2026-04-05-browser-automation-ai-agents-2026-landscape/

### Cloud Services
- **Browserbase:** https://www.browserbase.com/ — Stagehand v3: https://www.browserbase.com/blog/stagehand-v3
- **Steel Cloud:** https://app.steel.dev/sessions/
- **Bright Data Agent Browser:** https://brightdata.com/products/agent-browser
