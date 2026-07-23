# Matrix Research Browser — Fork and Feature Roadmap

> Canonical active roadmap after shelving the Phantom Browser prototype.
>
> **Goal:** Build a low-profile, Matrix-accented Chromium profile browser by forking MultiZen, then independently implementing selected Donut-inspired local/self-hosted features without bypassing third-party licensing or hosted entitlements.

## Direction

- Foundation candidate: `multizenteam/multizen-browser` (MIT app, Electron + React + patched Chromium integration).
- Donut is a feature/reference benchmark, not a source of proprietary services, branding, Wayfern binaries, or hosted entitlement bypasses.
- New product branding: Phantom Research / final name TBD; no Donut or MultiZen branding in distributed builds.
- Visual language: near-black surfaces, restrained Matrix green accent, cool gray text, minimal density, no noisy cyberpunk decoration.
- Target: Windows first; local-first profiles, persistent cookies, per-profile proxy, extensions, clean Chromium tabs, MCP/API, and per-profile 2FA workflow.

## Phase 0 — Source and license gate

- [ ] Fork/clone MultiZen into a new clean workspace; do not mix it into the old Phantom repo yet.
- [ ] Record exact commit, MIT license, dependency SBOM, and attribution requirements.
- [ ] Audit CloakBrowser/patched Chromium source and binaries separately; verify redistribution rights before packaging.
- [ ] Audit Donut feature references and classify each as: implement independently, reuse compatible open-source code, or defer.
- [ ] Confirm whether the chosen Chromium engine supports extension loading, persistent profiles, proxy auth, and normal tab/window lifecycle on Windows.

Exit gate: a written license/dependency matrix with no unclear runtime binary required for the first Windows build.

## Phase 1 — Clean Chromium profile baseline

- [ ] Build/rebrand locally with a new product name, bundle identifier, icons, updater URLs, and neutral attribution screen.
- [ ] Profile CRUD and isolated user-data directories.
- [ ] Persistent cookies/localStorage/IndexedDB across relaunch.
- [ ] Per-profile HTTP/SOCKS proxy, DNS/WebRTC leak checks, timezone/locale alignment.
- [ ] Normal Chromium tab/window behavior: create, activate, close, popup, close-last, restore.
- [ ] Benchmark 1, 10, 50, and 100 profiles for cold start, warm start, disk usage, and memory.

Exit gate: manual Windows smoke passes for profile launch/close, tab switching, persistence, proxy, and extension loading.

## Phase 2 — Donut-inspired local features

Implement only features with a clean licensing and ownership path:

- [ ] Profile groups and bulk launch/stop.
- [ ] Cookie import/export with explicit redaction and user confirmation.
- [ ] Extension manager and per-profile extension assignment.
- [ ] Local authenticated REST API + MCP with action capabilities, no fake CDP claims.
- [ ] Self-hosted encrypted sync, or defer until the local product is stable.
- [ ] Optional profile synchronizer after lifecycle and security review.

Do not:

- bypass Donut/Wayfern subscription checks;
- reuse Donut or Wayfern hosted endpoints/tokens;
- redistribute Wayfern binaries without written permission;
- ship a "Donut Pro unlocked" build;
- copy Donut branding, assets, or proprietary service code without a license review.

## Phase 3 — Per-profile 2FA

- [ ] Decide between a vetted WebExtension and a native encrypted TOTP vault.
- [ ] Store secrets per profile using Windows DPAPI/credential protection; never expose secrets to React, logs, URLs, MCP responses, or screenshots.
- [ ] Provide explicit `generate_totp`/`fill_totp` action with audit event containing no secret or code.
- [ ] Test persistence, backup/restore, clock skew, profile isolation, and emergency secret removal.

## Phase 4 — Branding and release

- [ ] Matrix Research theme tokens and accessibility contrast check.
- [ ] Windows native build, installer, portable ZIP, clean-machine smoke.
- [ ] License notices, source offer/corresponding source, SBOM, third-party notices.
- [ ] No release until engine redistribution and extension licenses are cleared.

## Immediate next work

1. Create a separate workspace for the MultiZen fork.
2. Run the source/license/runtime audit before touching UI.
3. Build the unmodified baseline and run the smallest Windows smoke.
4. Only then begin cosmetic rebrand and feature changes.

## Shelved project

`/root/projects/phantom-browser/` remains a historical prototype/reference. The 11 GB Rust target build artifact was removed on 2026-07-23; source and tests remain. Do not continue Phantom implementation unless the direction is explicitly reopened.
