# Nghiên cứu Kỹ thuật Xây dựng Antidetect Browser — Tài liệu cho Phantom Browser

**Ngày:** 2026-07-19
**Mục tiêu:** Tổng hợp primary sources về engine-level fingerprint spoofing, so sánh với JS/CDP injection,
đề xuất áp dụng cho Phantom Browser.

---

## Mục lục

1. [Tổng quan hệ sinh thái](#1-tổng-quan-hệ-sinh-thái)
2. [Engine-level (C++/Blink patching) vs JS/CDP injection](#2-engine-level-vs-js-cdp)
3. [Canvas, WebGL, Audio, Fonts, ClientRects](#3-canvas-webgl-audio-fonts-clientrects)
4. [UA-CH và Client Hints](#4-ua-ch-và-client-hints)
5. [TLS/HTTP2 Fingerprinting](#5-tls-http2-fingerprinting)
6. [WebRTC, DNS, Proxy Leaks](#6-webrtc-dns-proxy-leaks)
7. [Fingerprint Coherence & Persistence](#7-fingerprint-coherence--persistence)
8. [Phân tích các dự án cụ thể](#8-phân-tích-các-dự-án-cụ-thể)
9. [Khuyến nghị áp dụng cho Phantom](#9-khuyến-nghị-áp-dụng-cho-phantom)
10. [Tài liệu tham khảo](#10-tài-liệu-tham-khảo)

---

## 1. Tổng quan hệ sinh thái

Antidetect browser năm 2026 đã phát triển qua 3 thế hệ:

| Thế hệ | Phương pháp | Đại diện | Mức phát hiện |
|--------|------------|----------|---------------|
| 1.0 | JS injection, config flags | playwright-stealth, undetected-chromedriver | Rất dễ |
| 2.0 | CDP patch + runtime hook | Patchright, rebrowser-patches | Trung bình-Cao |
| 3.0 | C++ engine-level patch (Chromium/Firefox fork) | CloakBrowser, Camoufox, Clearcote, ShardX, fingerprint-chromium | Cực kỳ khó |

**Xu hướng hiện tại:** Toàn bộ dự án serious đều chuyển sang engine-level (C++/Blink patches).
JS injection không còn được coi là viable solution cho production anti-bot evasion.

---

## 2. Engine-level (C++/Blink patching) vs JS/CDP injection

### Engine-level (C++)

**Cách hoạt động:**
- Patch trực tiếp vào Chromium/Firefox source tree (Blink, V8, network stack)
- Compile thành binary — thay đổi ở mức native implementation
- Dẫn qua command-line flags hoặc CDP để cấu hình runtime

**Ưu điểm:**
- Không có seam nào để cross-check: native implementation *là* giá trị thật
- `toString()` trả về `[native code]` — không thể phân biệt với browser thật
- Tiếp cận được surfaces JS không thể chạm tới: TLS handshake, HTTP/2 frame order, GPU pipeline, worker threads
- Giá trị đồng nhất trên mọi execution context (iframe, worker, main thread)
- Per-site deterministic noise (dùng HMAC-SHA256 với domain) tránh được detection qua multiple reads

**Nhược điểm:**
- Cần build Chromium từ source (~40M dòng, hàng giờ build)
- Khó maintain khi Google thay đổi codebase
- Binary distribution phức tạp

### JS injection

**Cách hoạt động:**
- Dùng `Object.defineProperty`, Proxy, getter override trong JavaScript
- Inject qua CDP `Page.addScriptToEvaluateOnNewDocument`

**Vấn đề chính:**
- `Object.getOwnPropertyDescriptor` phát hiện getter không phải native
- `Function.prototype.toString()` không còn `[native code]`
- Worker thread không bị ảnh hưởng — detector spawn iframe và so sánh worker vs main thread
- Không thể chạm tới network stack (TLS, HTTP/2)

> **Nguồn Clearcote:** *"Engine-level wins for three concrete reasons: no JS-observable seam, reaches surfaces JavaScript can't touch, and applies uniformly across every execution context."*
> URL: https://www.clearcotelabs.com/research/how-a-stealth-browser-is-built-and-verified

> **Nguồn Camoufox:** *"All injected JavaScript is detectable — anti-bot systems can check Object.getOwnPropertyDescriptor, toString(), and window vs worker context."*
> URL: https://camoufox.com/stealth/

### CDP patch (Patchright approach)

**Cách hoạt động:**
- Patch Playwright source code (JavaScript/TypeScript) để sửa các CDP command gây leak
- Runtime patching — sửa Chromium binary tại runtime

**Giới hạn:**
- Driver-level, không phải engine-level — vẫn detectable nếu detector biết cách
- Chỉ che được automation protocol, không spoof được fingerprint

> **Nguồn Patchright docs:** Patchright modifies Playwright's driver code to evade CDP-based detection.
> URL: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright

---

## 3. Canvas, WebGL, Audio, Fonts, ClientRects

### 3.1 Canvas

**Cơ chế fingerprint:**
- `canvas.toDataURL()`, `canvas.getImageData()` — khác biệt nhỏ trong render phụ thuộc GPU/system font/subpixel rendering
- Anti-bot test bằng cách vẽ text + hình và hash kết quả

**Engine-level approaches:**

| Dự án | Cách xử lý |
|-------|-----------|
| **Clearcote** (patch 060) | Per-eTLD+1 farbling với HMAC-SHA256 seed — thêm deterministic noise vào `getImageData`/`toDataURL`. Grid-coherent measureText (đúng 1/512px grid). Canvas-bridge mode: forward canvas ops qua WebSocket để render trên real GPU |
| **CloakBrowser** | 1 trong 57 C++ patches — spoof canvas fingerprint |
| **Camoufox** | Firefox-level C++ intercept — spoof readback |
| **fingerprint-chromium** | Deterministic noise via seed, `--disable-spoofing=canvas` |

**Chi tiết Clearcote Canvas Bridge:**
```cpp
// Patches 060-canvas.patch + 065-canvas-bridge.patch
// Forward canvas operations to a real-GPU render host over WebSocket
// Returns authentic pixels/metrics coherent with the claimed GPU
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/060-canvas.patch

### 3.2 WebGL

**Cơ chế fingerprint:**
- `UNMASKED_VENDOR_RENDERER` — leak GPU thật
- `getParameter()` — hàng chục giá trị (MAX_TEXTURE_SIZE, aliased line width, shader precision)
- `getSupportedExtensions()` — khác nhau giữa GPU
- WebGPU: `navigator.gpu.requestAdapter()` leak GPUAdapterInfo

**Engine-level approaches:**

- **Clearcote** (patch 070, 075): Full getParameter table (WebGL1 + WebGL2 limits), getSupportedExtensions, GPU info — persona-driven. WebGPU adapter coherence bắt buộc coherent với WebGL GPU. `--disable-gpu-fingerprint` để dùng GPU thật coherent.
- **ShardX** (Chromium 149): WebGL/WebGPU spoofing engine-level.
- **fingerprint-chromium**: 3-tier GPU system: explicit > seed-derived > kill switch.

**Quan trọng:** WebGPU adapter (`navigator.gpu`) leak host GPU nếu không patch — CloakBrowser bị lỗi này.

### 3.3 Audio

- `AudioBuffer.getChannelData()` — khác biệt nhỏ do hardware/drivers
- `sampleRate`, `baseLatency`, `outputLatency`
- OfflineAudioContext rendering

**Clearcote approach (patch 020):**
```cpp
// Per-eTLD+1 farbling on AudioBuffer output
// Coherent sampleRate/baseLatency/outputLatency from persona
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/020-audio.patch

### 3.4 Fonts

**Cơ chế fingerprint:**
- `document.fonts.check()` — kiểm tra font tồn tại
- Font enumeration: `navigator.plugins`, CSS `@font-face`
- Canvas `measureText()` với font cụ thể

**Engine-level approaches:**

- **Clearcote** (patch 040): Engine allowlist (`font_cache.cc`) — expose persona font set. Metric-compatible clone substitution trên Linux: mỗi font Windows được map thành clone tương thích (Segoe UI → Selawik, Arial → Arimo, etc.) để advance-width check không phát hiện khác biệt.
- **ShardX**: Font enumeration pinned per profile at system level — match claimed device.
- **CloakBrowser**: JS-only font spoofing — host fonts vẫn leak qua CSS/canvas font-render.

> **Clearcote:** *"Every claimed Windows family renders PRESENT with a DISTINCT clone"*
> URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/040-fonts.patch

### 3.5 ClientRects

- `getBoundingClientRect()`, `Range.getClientRects()` — sub-pixel differences expose automation

**Clearcote approach (patch 050, 080):**
```cpp
// 050-shadow-dom: closed shadow root semantics
// 080-client-rects: sub-pixel jitter for client-rect geometry
// Then zeroed offset factor for grid-coherent rects (patch 060 fixed)
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/080-client-rects.patch

---

## 4. UA-CH (User-Agent Client Hints)

### Tổng quan

- `Sec-CH-UA` header mới thay thế User-Agent truyền thống
- High-entropy hints: architecture, bitness, model, platformVersion, uaFullVersion
- Low-entropy hints: brand, mobile, platform
- GREASE (RFC 8701) values được Chrome chèn vào để tránh fingerprinting

### Engine-level approaches:

- **Clearcote** (patch 010): Full UA + UA-CH spoofing (bitness=64, wow64=false, model=""). GREASE stability.
- **ShardX**: Full Sec-CH-UA stack với stable GREASE.
- **BrowserForge**: Headers generation với Sec-CH-UA matching browser profile.

**Vấn đề coherence:**
> *"UA mismatch vs UA-CH is an instant detection vector. Detector cross-references User-Agent against Sec-CH-UA* headers"*
> URL: https://www.clearcotelabs.com/research/coherence-over-camouflage

BrowserForge là thư viện Python sinh headers phù hợp thống kê với real-world traffic:
https://github.com/daijro/browserforge

---

## 5. TLS/HTTP2 Fingerprinting

### 5.1 JA3/JA4

**JA3:** MD5 hash của 5 fields TLS ClientHello: TLSVersion, Ciphers, Extensions, Curves, ECFormats.

**JA4:** Improved version — sorted extensions (chống randomization), SHA-256, support QUIC/HTTP3.

**Chrome 2023+ Extension Randomization:**
- Chrome bắt đầu randomize thứ tự TLS extensions từ 2023
- 16! ≈ 20 trillion possible JA3 hashes cho cùng browser
- Làm static scrapers dễ bị phát hiện hơn vì JA3 cố định trong khi browser thật thay đổi

### 5.2 Giải pháp

**curl-impersonate / curl_cffi:**
- Patch libcurl dùng BoringSSL (Chrome) hoặc NSS (Firefox)
- Tái tạo chính xác handshake: cipher suites, extension order, GREASE values
- Hỗ trợ các profile: chrome116, chrome124, chrome131, firefox117, firefox124
URL: https://github.com/lwthiker/curl-impersonate
URL: https://github.com/yifeikong/curl_cffi

**Clearcote (patch 210):**
```cpp
// --fingerprint-tls-profile=chrome-<major>
// Swaps version-variant fields: PQ key-share group (MLKEM>=131 / Kyber 124-130)
// and ALPS codepoint. Cipher list, sig algos, extension permut = real Chrome.
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/210-tls-network-persona.patch

**CloakBrowser:** TLS handshake matching; ShardX: JA4 match Chrome 149.

### 5.3 HTTP/2 Fingerprinting

- HTTP/2 SETTINGS frames order + value khác nhau giữa các browser
- curl-impersonate và engine-level patches đều sửa HTTP/2 parameters

> **Scrapfly:** *"curl-impersonate changes more than TLS — it adjusts HTTP/2 settings like header table size, window size, and stream priority to match real browsers."*
> URL: https://scrapfly.io/blog/posts/ja3-ja4-tls-fingerprinting-guide-to-detection-and-evasion

---

## 6. WebRTC, DNS, Proxy Leaks

### 6.1 WebRTC Leak

**Cơ chế:**
- WebRTC ICE candidates (STUN/TURN) leak real IP dù đang dùng proxy
- `enumerateDevices()` leak media devices thật

**Engine-level approaches:**

- **Clearcote** (patch 100): Fabricate server-reflexive candidate at proxy IP — send NO real STUN packet. Raw host candidates suppressed.
```cpp
// stun_port.cc: MaybePrepareStunCandidate fabricates srflx at proxy IP
// Skips SendStunBindingRequests entirely — no real STUN ever egresses host
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/100-webrtc-leak.patch

- **ShardX**: WebRTC over SOCKS5 UDP relay — candidates report proxy exit IP. TURN UDP/TCP/TLS + Voice all pass Twilio test. QUIC over UDP relay.
- **Camoufox**: WebRTC IP spoofing at protocol level (C++).
- **CloakBrowser**: WebRTC ICE fake candidates.

### 6.2 QUIC/HTTP3

- ShardX là dự án duy nhất hỗ trợ QUIC/HTTP3 over SOCKS5 UDP relay
- CloakBrowser: implemented but unstable — falls back to TCP
- Paid anti-detects: disable QUIC entirely khi proxy

### 6.3 DNS

- DNS leak prevention: proxy DNS qua SOCKS5/HTTP proxy
- Camoufox: blocks ads và trackers via DNS
- Clearcote: Network stack persona coherent

### 6.4 Geolocation

- Clearcote (patch 180): `--fingerprint-location` fabricated coordinates. Permission respected.
- ShardX: Auto-resolved timezone/locale/geolocation từ proxy exit country.
- CloakBrowser: Proxy-aware geo-location/timezone (geoip mode).

---

## 7. Fingerprint Coherence & Persistence

### 7.1 Coherence (tính nhất quán)

Đây là khái niệm quan trọng nhất trong antidetect năm 2026.

**Clearcote's "Coherence over camouflage":**
> *"Detection rarely asks 'is this value unusual?' — it asks 'do these values agree?'"*
> URL: https://www.clearcotelabs.com/research/coherence-over-camouflage

Các trục coherence phải đồng nhất:
- UA ↔ UA-CH (headers + navigator)
- GPU (WebGL renderer) ↔ CPU ↔ RAM ↔ OS (platform)
- Screen resolution ↔ viewport ↔ window size
- Timezone ↔ IP geolocation ↔ Accept-Language ↔ ICU locale
- TLS ClientHello ↔ claimed browser version
- Worker ↔ Main thread (canvas, WebGL, audio)
- Font list ↔ claimed OS

**Camoufox:**
> *"A Windows user agent with an Apple M1 GPU, a MacOS user agent with a Windows DirectX renderer — all impossible and will be flagged."*
> URL: https://camoufox.com/stealth/

### 7.2 Persistence

**Farbling model (Brave/Clearcote approach):**
- Deterministic per-eTLD+1 noise
- Session token + domain → HMAC-SHA256 → per-site seed
- Cùng site luôn cho cùng fingerprint trong session
- Khác site không linkable

**Clearcote:**
```cpp
// ungoogled::GetFarbleSeed64 mixes fingerprint seed with registrable domain
// Per-eTLD+1, stable per session
```
URL: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches/001-farble-seed-core.patch

**fingerprint-chromium:**
- 32-bit integer seed → deterministic random generator
- Per-session consistent

### 7.3 Coherence metrics (Clearcote's stealth coherence gate)

Clearcote có `scripts/stealth_coherence.py` — test tự động đo:
- measuretext-grid: TextMetrics trên Chrome's 1/512px dyadic grid
- worker-vs-main: OffscreenCanvas vs main thread
- bcr-vs-range: getBoundingClientRect vs Range rects

Nếu fail → build không pass — regression prevention.

---

## 8. Phân tích các dự án cụ thể

### 8.1 CloakBrowser
| Thuộc tính | Giá trị |
|-----------|---------|
| **Base** | Chromium (fork) |
| **Phương pháp** | 57 C++ source patches |
| **Trạng thái** | Binary closed-source (engin đang sau subscription). Patched binary closed-source |
| **Giá** | Từng free, nay subscription |
| **Coherence** | Thấp — generator sinh incoherent fingerprints (Win UA + Mac GPU, mobile UA + desktop screen) |
| **WebGPU** | ❌ untouched — host GPU leaks |
| **Fonts** | ❌ JS-only — host fonts leak qua CSS/canvas |
| **TLS** | ⚠️ static / drifts |
| **QUIC** | ⚠️ implemented but unstable |
| **Launcher** | CLI only, không GUI |
| **Test pass** | 30/30 (2026-05) |
| **Source** | https://github.com/CloakHQ/CloakBrowser |

**Website:** https://cloakbrowser.dev/

### 8.2 Camoufox
| Thuộc tính | Giá trị |
|-----------|---------|
| **Base** | Firefox (fork) |
| **Phương pháp** | C++ engine patches (Firefox) |
| **Trạng thái** | Open source (từ v146.0.1-beta.25). Đang active development |
| **Generator** | BrowserForge (Bayesian network, real-world distribution) |
| **Coherence** | Medium — "doesn't always succeed", anti-bot providers tìm inconsistency |
| **Automation** | Juggler patched — sandboxed Page Agent |
| **Headless** | Patched to appear as normal window |
| **Mouse** | Human-like C++ algorithm |
| **Source** | https://github.com/daijro/camoufox |
| **Docs** | https://camoufox.com/stealth/ |

**Note:** Daijro (author) stepped down, transferred to Clover Labs. Camoufox gặp vấn đề performance do base Firefox version gap + fingerprint inconsistencies được phát hiện.

### 8.3 Clearcote
| Thuộc tính | Giá trị |
|-----------|---------|
| **Base** | Ungoogled Chromium 149 |
| **Phương pháp** | 30+ plain unified .patch files (open, auditable) |
| **Trạng thái** | Open source (MIT-like). Release binary có sẵn |
| **Coherence** | Cao nhất — mỗi giá trị derive từ một persona seed duy nhất. Cross-API coherence gate |
| **TLS** | ✅ --fingerprint-tls-profile |
| **WebGPU** | ✅ Full coherence với WebGL |
| **Fonts** | ✅ Engine allowlist + metric-compatible clones trên Linux |
| **Canvas** | ✅ Farble + Canvas Bridge (real GPU render) |
| **WebRTC** | ✅ No STUN leak — fabricate proxy IP candidate |
| **Launcher** | SDK (Python/Node/.NET) + browser binary |
| **Source** | https://github.com/clearcotelabs/clearcote-browser |
| **Research** | https://www.clearcotelabs.com/research |

**Điểm mạnh:** Toàn bộ research công khai, reproducible builds, patch set auditable.

### 8.4 ShardX (ShardBrowser)
| Thuộc tính | Giá trị |
|-----------|---------|
| **Base** | Chromium 149 (binary closed-source) |
| **Phương pháp** | Engine-level patches (engine binary closed-source) |
| **Trạng thái** | Launcher MIT, engine closed-source |
| **Profiles** | 170 starter profiles (real device samples) |
| **TLS** | ✅ Chrome 149 match |
| **WebGPU** | ✅ Full |
| **WebRTC/QUIC** | ✅ SOCKS5 UDP relay end-to-end |
| **Launcher** | Desktop UI + HTTP API + MCP + SDKs |
| **Source** | https://github.com/ProxyShard/ShardBrowser |

**Điểm mạnh:** 170+ real device profiles, QUIC + WebRTC over SOCKS5, tích hợp proxy tốt.

### 8.5 fingerprint-chromium
| Thuộc tính | Giá trị |
|-----------|---------|
| **Base** | Ungoogled Chromium |
| **Phương pháp** | C++ patches |
| **Trạng thái** | Open source (delayed source release) |
| **Seed** | 32-bit integer |
| **Flags** | `--fingerprint`, `--fingerprint-brand`, `--fingerprint-gpu-vendor/renderer`, `--disable-spoofing` |
| **Source** | https://github.com/adryfish/fingerprint-chromium |

### 8.6 BrowserForge
- Thư viện Python sinh headers và fingerprints
- Bayesian generative network mô phỏng real-world traffic distribution
- Tích hợp với Camoufox
- Không phải browser engine — chỉ sinh data
- URL: https://github.com/daijro/browserforge

### 8.7 Patchright
- Patch Playwright tại driver level để tránh CDP detection
- Không spoof fingerprint — chỉ ẩn automation signals
- URL: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright

---

## 9. Khuyến nghị áp dụng cho Phantom

### 9.1 Lựa chọn nền tảng

**Khuyến nghị:** **Chromium** (không phải Firefox)

Lý do:
1. Chromium engine đang là mục tiêu chính của phần lớn các anti-bot systems
2. Tài liệu nhiều hơn, cộng đồng lớn hơn (CloakBrowser, Clearcote, ShardX, fingerprint-chromium)
3. Phần lớn users target Chromium-based browsers
4. WebGPU, WebRTC, TLS patches đều mature hơn trên Chromium
5. Playwright/Puppeteer ecosystem

Tuy nhiên, Camoufox (Firefox) có điểm mạnh: Juggler protocol lower-level hơn CDP, khó detect hơn.
Nếu Phantom có thể maintain cả 2 engines, điều này là lý tưởng.

### 9.2 Phương pháp: Engine-level patches là bắt buộc

Phantom **không thể** chỉ dựa vào JS injection hay CDP config.
Cần ít nhất:

**Tối thiểu (Phase 1):**
- Patch UA + UA-CH (navigator + headers)
- Patch canvas fingerprint (toDataURL, getImageData)
- Patch WebGL UNMASKED_VENDOR/RENDERER
- Patch AudioContext
- Hide navigator.webdriver + automation flags
- Patch WebRTC IP leak (STUN suppression)
- Patch headless mode

**Nâng cao (Phase 2):**
- Full WebGL getParameter table (coherent with claimed GPU)
- WebGPU adapter coherence
- Font enumeration engine-level
- TLS ClientHello persona (JA3/JA4 match)
- Per-eTLD+1 farbling (Brave/Clearcote model)
- Client rects coherence
- Multi-screen APIs
- Humanize input (mouse, keyboard, scroll)

**Advanced (Phase 3):**
- Canvas Bridge (forward rendering to real GPU)
- QUIC/HTTP3 over SOCKS5 UDP relay
- Manifest V3 extension support
- Screenshare/WebAudio coherence
- Automation protocol isolation

### 9.3 Kiến trúc đề xuất

```
Phantom Architecture
├── Patched Chromium Engine (C++ patches)
│   ├── Blink/V8 patches (canvas, WebGL, audio, fonts)
│   ├── Network stack patches (TLS, HTTP2, QUIC)
│   ├── WebRTC patches (STUN leak prevention)
│   └── Automation patches (CDP, webdriver)
├── Fingerprint Generator (BrowserForge-like)
│   ├── Bayesian network for coherent profiles
│   ├── Real-world distribution matching
│   └── Per-session seed management
├── Profile Manager
│   ├── Profile isolation (user-data-dir)
│   ├── Proxy binding (SOCKS5, HTTP, WireGuard)
│   ├── Cookie and storage persistence
│   └── Fingerprint library (real device samples)
├── Automation API
│   ├── CDP-based (Playwright-compatible)
│   ├── REST API for profile management
│   └── MCP server for AI agents
└── Stealth Coherence Gate
    ├── Worker-vs-main consistency tests
    ├── Cross-API coherence verification
    └── Regression prevention suite
```

### 9.4 Priority roadmap

| Giai đoạn | Tính năng | Nguồn tham khảo chính |
|-----------|----------|----------------------|
| **P0** | Fork Chromium, build pipeline, patch system | Clearcote BUILDING.md, ungoogled-chromium |
| **P0** | UA + UA-CH + navigator spoofing | Clearcote patch 010, BrowserForge |
| **P0** | Canvas + WebGL (+WebGPU) spoofing | Clearcote patches 060, 065, 070, 075 |
| **P0** | Audio farbling | Clearcote patch 020 |
| **P0** | WebRTC leak suppression | Clearcote patch 100 |
| **P0** | Profile isolation + proxy binding | ShardX, Donut |
| **P1** | Font enumeration engine-level | Clearcote patch 040 |
| **P1** | Client rects / shadow DOM coherence | Clearcote patches 050, 080 |
| **P1** | Timezone + locale + ICU coherence | Clearcote patches 090, 092 |
| **P1** | Fingerprint generator (Bayesian) | BrowserForge, Clearcote persona engine |
| **P1** | TLS network persona | Clearcote patch 210, curl-impersonate |
| **P2** | Screen/media queries/device sensors | Clearcote patches 140-150 |
| **P2** | Speech synthesis + media devices | Clearcote patches 170, 148 |
| **P2** | Humanized input (mouse/keyboard) | Clearcote patch 130, Camoufox |
| **P2** | Storage/memory/connection coherence | Clearcote patches 145, 146, 150 |
| **P2** | Per-eTLD+1 farbling | Clearcote patch 001, Brave |
| **P3** | Canvas Bridge (real GPU rendering) | Clearcote patch 065 |
| **P3** | QUIC/HTTP3 over SOCKS5 | ShardX approach |
| **P3** | MCP/REST API | ShardX, Donut |
| **P3** | 170+ real device profile library | ShardX approach |

### 9.5 Critical lessons từ các dự án

1. **Coherence > Camouflage:** Đừng tối ưu từng signal riêng lẻ. Tất cả phải agree từ 1 seed duy nhất. (Nguồn: Clearcote research)

2. **Worker leak là killer:** Nếu main thread spoofed nhưng worker không → instant detection. Fix bằng engine-level patches áp dụng uniform. (Nguồn: Clearcote stealth coherence gate)

3. **TLS là layer không thể bỏ qua:** JA3/JA4 fingerprint được kiểm tra TRƯỚC cả HTTP headers. Chrome extension randomization đã biến static TLS fingerprint thành bot signature. (Nguồn: Scrapfly, curl-impersonate)

4. **Fonts là minefield:** JS-only font spoofing không đủ — detector check qua canvas measureText, CSS @font-face, enumeration APIs. Cần engine-level font allowlist + metric-compatible clones. (Nguồn: Clearcote, ShardX)

5. **WebGPU là detection vector mới:** `navigator.gpu.requestAdapter()` leak host GPU. Nếu WebGL nói Intel nhưng WebGPU nói NVIDIA → flag. Nhiều dự án (CloakBrowser) bỏ qua cái này. (Nguồn: ShardX comparison table)

6. **Automation protocol footprint:** CDP có detectability riêng. Juggler (Firefox) lower-level hơn CDP, khó detect hơn. Patchright approach (patch Playwright) có thể tạm thời giải quyết. (Nguồn: Camoufox, Patchright)

7. **Reproducible builds:** Nếu Phantom muốn được trusted, cần reproducible builds + open patches như Clearcote. (Nguồn: Clearcote build philosophy)

### 9.6 Các dự án nên tham khảo source code

| Dự án | URL | Nên học hỏi |
|-------|-----|------------|
| Clearcote | https://github.com/clearcotelabs/clearcote-browser | Patch structure, coherence model, farbling, TLS persona, Canvas bridge |
| CloakBrowser | https://github.com/CloakHQ/CloakBrowser | Scale of patches (57), test results |
| Camoufox | https://github.com/daijro/camoufox | Firefox approach, Juggler sandboxing, humanize algo |
| ShardX | https://github.com/ProxyShard/ShardBrowser | Profile management, QUIC/UDP relay, 170 profiles |
| fingerprint-chromium | https://github.com/adryfish/fingerprint-chromium | Seed system, CLI flags architecture |
| BrowserForge | https://github.com/daijro/browserforge | Bayesian fingerprint generator |
| curl-impersonate | https://github.com/lwthiker/curl-impersonate | TLS impersonation technique |
| Ungoogled-Chromium | https://github.com/ungoogled-software/ungoogled-chromium | Base cho Phantom patches |

---

## 10. Tài liệu tham khảo (URIs đầy đủ)

### Primary Sources (Source Code)
- Clearcote patches: https://github.com/clearcotelabs/clearcote-browser/tree/main/patches
- CloakBrowser: https://github.com/CloakHQ/CloakBrowser
- Camoufox: https://github.com/daijro/camoufox
- ShardX: https://github.com/ProxyShard/ShardBrowser
- BrowserForge: https://github.com/daijro/browserforge
- Donut Browser: https://github.com/zhom/donutbrowser
- Wayfern: https://github.com/zhom/wayfern-humanize
- fingerprint-chromium: https://github.com/adryfish/fingerprint-chromium
- Patchright: https://github.com/Kaliiiiiiiiii-Vinyzu/patchright
- curl-impersonate: https://github.com/lwthiker/curl-impersonate
- curl_cffi: https://github.com/yifeikong/curl_cffi

### Research & Documentation
- Clearcote: "How a stealth browser is built and verified": https://www.clearcotelabs.com/research/how-a-stealth-browser-is-built-and-verified
- Clearcote: "Coherence over camouflage": https://www.clearcotelabs.com/research/coherence-over-camouflage
- Camoufox Stealth Overview: https://camoufox.com/stealth/
- Camoufox Introduction: https://camoufox.com/
- Scrapfly JA3/JA4 Guide: https://scrapfly.io/blog/posts/ja3-ja4-tls-fingerprinting-guide-to-detection-and-evasion
- curl-impersonate 2026 Guide: https://dataresearchtools.com/browser-tls-fingerprint-mimicry-with-curl-impersonate-2026/
- CloakBrowser Guide: https://www.easytool.me/blog/cloakbrowser-stealth-chromium-bot-detection-bypass-guide
- Fingerprint-chromium Architecture: https://deepwiki.com/adryfish/fingerprint-chromium/5-technical-architecture
- Camoufox DeepWiki: https://deepwiki.com/daijro/camoufox/5-fingerprinting-and-privacy
- BrowserForge DeepWiki: https://deepwiki.com/daijro/browserforge/3-usage-guide

### Anti-Bot Testing Tools
- BrowserLeaks (Canvas, TLS, WebRTC): https://browserleaks.com/
- FingerprintJS Demo: https://fingerprint.com/demo/
- Bot.sannysoft: https://bot.sannysoft.com/
- CreepJS: https://abrahamjuliot.github.io/creepjs/
- Browserscan: https://www.browserscan.net/
- Pixelscan: https://pixelscan.net/
- fp.haru.gay: https://fp.haru.gay/
- reCAPTCHA Score Detector: https://antcpt.com/score_detector/

---

*Tài liệu được tổng hợp ngày 2026-07-19 dựa trên primary sources và source code mới nhất.
Khuyến nghị cập nhật hàng tháng vì Chrome/Firefox updates có thể thay đổi fingerprint surface.*
