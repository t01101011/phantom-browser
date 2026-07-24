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

**Implementation update — 2026-07-23**

- MultiZen fork is live at `t01101011/multizen-browser`; local workspace: `/root/projects/phantom-research`.
- Source/runtime audit merged in PR #1 (`a544f0d`); pinned upstream MultiZen `0871ad3` and CloakBrowser wrapper `36390b5`.
- MultiZen app source is MIT. CloakBrowser wrapper source is MIT, but its compiled browser binary has separate proprietary terms and may not be bundled/redistributed without written OEM permission.
- Native Windows baseline merged in PR #2 (`c385ae7`). CI run `29997645879` passed install, typecheck, Windows unpacked + NSIS build, package acceptance, cold-start window, MCP token initialization, and shutdown.
- Chrome for Testing is now the safe default. CloakBrowser remains explicit opt-in for internal evaluation only.
- Windows artifact `multizen-windows-baseline-c704884ea99a982e5621d482df09045255dedca7` passed tk's manual Windows review on 2026-07-23: app startup, profile launch/stop, tabs + restore, cookie persistence, extension loading, and proxy IP/DNS/WebRTC checks all passed.
- SBOM/feature ownership audit merged in PR #3 (`bb31fd5`): CycloneDX inventory covers 521 required components, `THIRD_PARTY_NOTICES.txt` is generated, first-party workspace packages declare MIT, and Donut-inspired capabilities are classified into independent implementation/defer/do-not-reuse boundaries.

- [x] Fork/clone MultiZen into a new clean workspace; do not mix it into the old Phantom repo yet.
- [x] Record exact commits and root/source license boundaries.
- [x] Generate dependency SBOM and third-party attribution inventory.
- [x] Audit CloakBrowser/patched Chromium source and binaries separately; block redistribution pending written rights.
- [x] Audit Donut feature references and classify each as: implement independently, reuse compatible open-source code, or defer.
- [x] Confirm source support for extension loading, persistent profiles, proxy auth, and normal tab/window lifecycle.
- [x] Produce and cold-start a native Windows CFT baseline artifact.
- [x] Complete tk's manual Windows smoke: profile CRUD/launch, tabs/popups/restore, persistence, extension loading, HTTP/SOCKS proxy, DNS/WebRTC leak checks.

Exit gate: **passed for internal development**. Source/runtime boundaries, SBOM inventory, native Windows build, and manual Windows behavior/proxy checks are verified. External distribution still requires final runtime notice texts and explicit clearance for any optional proprietary browser binary.

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

**Status update — 2026-07-24**

- Product/package identity rebrand merged in PR #4 (`5cc1798`).
- Profile groups, explicit multi-select bulk launch/stop, and Windows launch/session fixes merged in PR #5 (`a6d6a2c`).
- Encrypted `.mzar` archive hardening merged in PR #6 (`6bdba3d`): explicit secret-content warning, stronger new-export passphrases, malformed archive validation, and failed-import rollback.
- Full GUI rebrand cleanup **merged** in PR #7 (`212effd`) after tk acceptance: remaining user-visible copy, native dialogs, updater/MCP/extension surfaces, neutral MIT attribution, fork release target, and Windows artifact label are updated while compatibility internals remain unchanged. The Windows shell now uses one compact 44px custom titlebar with native caption controls, platform-aware insets, and corrected Phantom Browser brand alignment. tk's supplied transparent logo is the canonical source for app/installer/renderer/companion icons. Windows EXE icon embedding is enforced with multi-size `build/icon.ico`, `signAndEditExecutable: true`, and a native smoke that extracts the icon from `Phantom Browser.exe` and pixel-compares it with the canonical ICO. Final native Windows run `30090079128` passed; accepted artifact: `phantom-browser-windows-ae19000ec73dab1fbfce261c72521361a4c561da` (221,329,104 bytes).
- Phantom Research design-system slice **merged** in PR #8 (`2dd2bb4`) after tk acceptance: linted `DESIGN.md`, near-black/spectral-green tokens, typography/surface rules, app-shell navigation, title/search bar, flat primary action, profile toolbar/table/default view/row-selection treatment, and renderer-wide removal of legacy purple/pink accents. CI recursively scans renderer TSX/CSS and blocks regressions. Final native Windows run `30093778155` passed; accepted artifact: `phantom-browser-windows-a28e92374d38cc8000f3c33d988ccbed928fae84`.
- Primary-action shortcut cleanup **merged** in PR #9 (`1e9aaa1`) after tk acceptance: removed the visually awkward Command/Ctrl+N badge from `New profile` while preserving the actual keyboard shortcut. Final native Windows run `30095822894` passed; accepted artifact: `phantom-browser-windows-2fd16544e67acad3b32df5c5d3f29b0959125258`.

### Next-session handoff

Start with **Phase 4A — remaining-screen design-system rollout** in `/root/projects/phantom-research` from current `master` (`1e9aaa1`). Create a fresh feature branch and a new Notion task under project `399539c8-7ba9-811c-9b07-d0f19fb583ce`; do not reopen the completed PR #8/#9 tasks.

Scope the next PR to visual consistency only—no extension-manager feature work yet:

1. Audit profile grid/detail/create/edit flows, Proxy, Extensions, MCP, Settings, onboarding, dialogs, and loading/empty/error states against root `DESIGN.md`.
2. Replace one-off inline colors, radii, borders, and focus treatments with shared Phantom tokens/classes while preserving compatibility internals (`@multizen/*`, `window.multizen`, IPC/localStorage/data/archive names).
3. Keep `#42F58D` reserved for selected/active/focus/primary states; semantic success/warning/error/info colors stay distinct. Do not reintroduce purple/pink branding, glow, or gradients.
4. Preserve keyboard behavior and persisted preferences. Avoid decorative shortcut chips inside primary buttons unless they pass real Windows visual review.
5. Extend `scripts/check-phantom-design-system.cjs` with a fail-first contract for each migrated surface, then run immutable install, typecheck, all acceptance checks/tests, Linux package smoke, and native Windows CI.
6. Hand off the Windows artifact for 100% and 125% scaling review. Merge only after tk explicitly accepts it.

After Phase 4A merges, proceed in order: extension manager and per-profile/group assignment; 1/10/50/100-profile benchmark; native Chromium anti-detect coverage audit; final runtime/license/release readiness.

1. Continue the design-system rollout to profile grid/detail/create flows, proxy, extensions, MCP, settings, onboarding, dialogs, loading/empty/error states, and motion.
2. Implement extension manager improvements and per-profile/group extension assignment.
3. Benchmark 1/10/50/100 profiles for startup, memory, and disk behavior.
4. Research native Chromium anti-detect coverage for canvas/audio/font/DOMRect. Do not ship naive JS spoofing as a substitute for native patches.
5. Resolve final runtime notices and optional-engine licensing before any external release.

## Shelved project

`/root/projects/phantom-browser/` remains a historical prototype/reference. The 11 GB Rust target build artifact was removed on 2026-07-23; source and tests remain. Do not continue Phantom implementation unless the direction is explicitly reopened.
