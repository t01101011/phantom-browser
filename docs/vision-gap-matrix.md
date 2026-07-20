# Phantom Browser — Vision target and gap matrix

Date: 2026-07-19
Sources: public Vision website/docs and FoxDesk source/release pipeline. This is a functional product benchmark, not a plan to copy proprietary source, branding, or assets.

## Target definition

Phantom should become a local-first, cross-platform profile browser with two equally supported surfaces:

1. Human desktop GUI for profile/folder/proxy/session management.
2. Stable local API for autonomous agents and external Playwright clients.

Windows and Linux are first-class. Linux must support both headed desktop and headless service/container operation.

## What Phantom already has

- Camoufox engine with persisted coherent BrowserForge identity.
- Per-profile user-data directories and cookie/session persistence.
- SQLite profile store.
- Proxy per profile and duplicate warning.
- Create/list/get/delete, launch/stop/status/log-tail sidecar actions.
- React profile table and basic Tauri shell.
- Linux determinism and process cleanup probes.

## Missing compared with FoxDesk

- Windows-native CI build and runtime acceptance tests.
- Frozen backend/browser worker; current external venv setup is fragile.
- Installer and tested portable build.
- Readiness probe before opening the desktop webview.
- Cross-platform process tree tracking with psutil/job objects.
- Edit/clone/import/export profiles, groups/tags and bulk actions.
- Proxy pool, health checks, assignment policies and encrypted credentials.
- Cookie import/export.
- Settings/setup/update/diagnostics UX.
- Session concurrency limit, idle timeout and stop-all.
- Authenticated localhost API and explicit browser worker protocol.
- Automated packaging/session tests.

## Missing compared with Vision

### Product/UI

- Folder hierarchy and per-folder defaults (extensions, bookmarks, start pages).
- Extension library.
- Profile history/audit trail and restore points.
- Team workspace, roles and folder-level permissions.
- Synchronizer for mirroring input across selected profiles.
- Cross-device encrypted profile sync.
- 2FA/TOTP helper.
- Webcam/video spoofing.
- Proxy traffic optimization/static cache.
- SOCKS5 UDP/WebRTC routing.

### API and agent surface

- Versioned HTTP API on localhost with token auth.
- Persistent-profile start/stop/list endpoints returning an automation endpoint.
- Instant/ephemeral profiles with optional fingerprint, proxy, cookies, extensions and behavior; return cookies/artifacts on close.
- External Playwright/Puppeteer/Selenium connection contract.
- Agent leases, TTL, cancellation and idempotency keys.
- Structured events/logs, health/readiness endpoints and failure codes.
- Screenshot/DOM/accessibility-tree/artifact endpoints.
- Human-like input primitives (type, mouse move/click, scroll) with deterministic seeds and policy controls.
- Resource quotas, concurrency queue and crash recovery.

## Recommended architecture

### Control plane

- Python FastAPI service as the single source of truth.
- SQLite initially; schema includes profiles, folders, proxies, sessions, leases, jobs, events and artifacts.
- Bind to `127.0.0.1` by default; random local token; never expose unauthenticated LAN API.
- Desktop shell is only a client of this API.

### Engine workers

- One isolated worker process per running profile.
- `psutil`-based process discovery/cleanup on Windows and Linux; Windows Job Object where possible; Linux process group/cgroup in service mode.
- Camoufox remains the default persistent identity engine.
- Add a Chromium-compatible engine as a second backend for CDP-first agents and Chromium-only sites; do not pretend Firefox Playwright transport is CDP.
- Common worker contract: start, ready, endpoint, heartbeat, stop, export artifacts.

### Desktop and service modes

- Windows: build/package on a Windows CI runner; produce installer + portable ZIP + checksums.
- Linux desktop: packaged desktop shell plus backend.
- Linux agent/server: no desktop dependency; run API + workers headless under systemd or Docker with persistent volumes.
- Avoid requiring users to install a project venv manually for release builds.

### Agent-first API

Minimum useful contract:

- `POST /v1/profiles`, `GET/PATCH/DELETE /v1/profiles/{id}`
- `POST /v1/profiles/{id}/sessions`, `DELETE /v1/sessions/{id}`
- `POST /v1/sessions/instant`
- `GET /v1/sessions`, `GET /v1/sessions/{id}`
- `POST /v1/sessions/{id}/lease`, heartbeat/release
- `GET /v1/sessions/{id}/events`
- `POST /v1/sessions/{id}/artifacts/{screenshot|cookies|storage}`
- Engine-specific connection descriptor: Playwright transport for Camoufox; CDP URL for Chromium.

## Priority

### P0 — stop shipping broken foundations

- Replace ad-hoc Linux cross-compiled Windows hand-off with Windows CI packaging.
- Add release artifact smoke tests on actual Windows and Linux runners.
- Introduce FastAPI control plane, readiness probe and token auth.
- Normalize worker lifecycle and crash recovery.

### P1 — Vision-like core plus agents

- Folder/profile/proxy CRUD, clone/import/export and bulk actions.
- Persistent and instant sessions.
- External automation connection contract.
- Leases, TTL, queue/concurrency limits, structured logs/events and artifacts.
- Headless Linux service/container mode.

### P2 — operator productivity

- Extension/bookmark/start-page library.
- Cookie import/export, proxy pool health, history/restore.
- Synchronizer and human-like input library.
- Diagnostics and updater.

### P3 — hard systems work

- Team sync/RBAC and encrypted cloud profile storage.
- SOCKS5 UDP/WebRTC tunneling and proxy traffic cache.
- Webcam/video spoofing.
- Real-device fingerprint corpus and continuous anti-fraud validation.

## Key warning

Vision claims fingerprints sampled from real devices, UDP-over-SOCKS5, webcam spoofing and custom Chromium CDP commands. These are engine/network products, not normal GUI features. Camoufox + BrowserForge cannot honestly claim parity by adding form fields. They need separate engineering and validation tracks.
