# Phantom Browser Full GUI Rebrand Cleanup Plan

> **For Hermes:** Use test-driven-development and execute this plan task-by-task. Do not rename internal compatibility surfaces merely to remove upstream terminology.

**Goal:** Finish the user-facing Phantom Browser rebrand without breaking existing profiles, archives, IPC, package imports, or local settings.

**Architecture:** Separate public identity from compatibility internals. Replace strings and assets visible to users, update CI/release labels, and add neutral upstream attribution. Preserve `@multizen/*`, `window.multizen`, `.mzar`, archive magic, existing data paths, and persisted storage keys.

**Tech Stack:** Electron, React, TypeScript, electron-builder, GitHub Actions, Node test runner.

---

## Current state

- Canonical repository: `https://github.com/t01101011/phantom-browser`
- Workspace: `/root/projects/phantom-research`
- Base branch: `master`
- Latest merged work:
  - PR #4 identity/package rebrand
  - PR #5 profile groups, multi-select bulk lifecycle, Windows launch fixes
  - PR #6 encrypted archive hardening
- Product identity already set to `Phantom Browser`, but many GUI strings and several assets/CI labels still say MultiZen.
- Before implementation, create/find the matching Notion task under project `399539c8-7ba9-811c-9b07-d0f19fb583ce`, set execution mode, and move it to `In Progress`.

## Scope

### Replace user-facing branding

Audit and replace user-visible `MultiZen` references in:

- `apps/desktop/src/renderer/src/components/UpdateBanner.tsx`
- `apps/desktop/src/renderer/src/components/onboarding/ChromiumBootstrapModal.tsx`
- `apps/desktop/src/renderer/src/components/onboarding/FirstRun.tsx`
- `apps/desktop/src/renderer/src/components/screens/Settings.tsx`
- `apps/desktop/src/renderer/src/components/mcp/McpPanel.tsx`
- `apps/desktop/src/renderer/src/components/profile/ExtensionsSection.tsx`
- `apps/desktop/src/renderer/src/components/atoms/Cube.tsx`
- `apps/desktop/src/main/index.ts`
- `apps/desktop/src/main/ChromiumBootstrap.ts`
- `apps/desktop/src/main/ChromiumBrowserDriver.ts` for native authorization prompts only
- `apps/desktop/src/main/proxyGeo.ts` for the HTTP user-agent

### Replace visual assets

Audit and replace:

- renderer logo imported by `apps/desktop/src/renderer/src/components/atoms/Cube.tsx`
- app/installer icons referenced by `apps/desktop/electron-builder.yml`
- companion extension icons under `apps/desktop/resources/companion/`

Use a restrained Phantom Browser mark compatible with the current dark UI. Do not redesign the whole palette in this slice.

### Update CI/release labels

- Rename Windows artifact in `.github/workflows/windows-baseline.yml` from `multizen-windows-baseline-*` to `phantom-browser-windows-*`.
- Ensure installer, unpacked executable, AppImage and release labels already use Phantom Browser naming.

### Add neutral attribution

Add a concise About/Settings attribution such as:

> Phantom Browser is based on MultiZen, licensed under MIT. Third-party notices are included with the distribution.

Link or point users to `THIRD_PARTY_NOTICES.txt` where practical. Do not imply affiliation or endorsement.

## Explicit compatibility boundary — do not rename

Keep these unchanged unless a separate migration plan is approved:

- workspace packages `@multizen/*`
- preload/global API `window.multizen`
- IPC channel namespace
- `.mzar` extension and `MZAR` archive magic
- existing localStorage keys (`multizen.ui.*`)
- profile database and user-data paths used by existing installations
- internal source comments when they accurately describe upstream compatibility and are not user-visible

## Implementation sequence

### Task 1: Add a failing user-facing branding acceptance check

**Files:**
- Create: `scripts/check-phantom-gui-rebrand.cjs`
- Modify: `.github/workflows/windows-baseline.yml`

The check should scan only public/user-visible surfaces and fail on forbidden strings such as `MultiZen` in renderer copy, native dialog labels, updater text, companion CTA text, and artifact names. Maintain an explicit allowlist for compatibility internals.

Run:

```bash
node scripts/check-phantom-gui-rebrand.cjs
```

Expected before implementation: FAIL with exact paths/strings.

### Task 2: Replace renderer and native-dialog copy

Update the exact files listed under “Replace user-facing branding.” Keep wording concise and consistent: always `Phantom Browser`, not `Phantom Research`, `Matrix Research`, or bare `Phantom`.

Run the acceptance check again; remaining failures should now be asset/CI/attribution related.

### Task 3: Add attribution and notices pointer

Modify `apps/desktop/src/renderer/src/components/screens/Settings.tsx` or the existing About section. Add the neutral MIT attribution and notices reference without cluttering the main profile UI.

Add/update a focused string-level acceptance assertion in `scripts/check-phantom-gui-rebrand.cjs`.

### Task 4: Replace logo/icon assets

Create/replace the relevant PNG/ICO/ICNS assets. Verify required dimensions and transparency. Update `electron-builder.yml` only if paths change.

Do not copy Donut, Wayfern, MultiZen, Chrome, or third-party branding.

### Task 5: Rename CI and release-facing labels

Modify `.github/workflows/windows-baseline.yml` and any release config containing old artifact labels. Do not rename internal workspace/package identifiers.

### Task 6: Verify locally

Run in this order:

```bash
yarn install --immutable
yarn typecheck
node scripts/check-phantom-rebrand.cjs
node scripts/check-phantom-gui-rebrand.cjs
yarn workspace @multizen/desktop build:linux
git diff --check
```

Verify the AppImage/artifact filename contains `Phantom Browser` or `phantom-browser`, as appropriate.

### Task 7: Windows CI and manual visual smoke

Open a PR and wait for Windows CI. Manual Windows review must check:

1. app/installer icon
2. top bar and window title
3. onboarding/bootstrap modal
4. Settings/About attribution
5. update banner copy
6. MCP panel copy
7. Chrome Web Store companion CTA and native confirmation
8. startup/error dialogs
9. CI artifact name
10. existing profile/session/archive compatibility

Move Notion task to `Review` with PR, commit, CI run and artifact evidence. Only tk approval moves it to `Done` and permits merge.

## Acceptance criteria

- No user-visible MultiZen branding remains in packaged Phantom Browser surfaces.
- Product is consistently called `Phantom Browser`.
- New logo/icons render correctly in app, installer and companion extension.
- Neutral MIT attribution is present.
- Existing profiles, settings and `.mzar` archives continue to work.
- Internal compatibility namespaces remain unchanged.
- Local checks, Linux build and Windows CI pass.
- tk completes manual visual smoke before merge.

## Risks

- Blanket search/replace can break package imports, IPC or persisted data. Use scoped replacements and an allowlist.
- Icon formats may build on Linux but fail electron-builder on Windows; verify native CI artifact.
- Renaming user-data paths would make existing profiles appear missing; explicitly forbidden in this slice.
- Attribution must be factual and neutral, not presented as endorsement.

## Deferred after this PR

1. Extension manager and per-profile/group extension assignment.
2. Performance benchmark at 1/10/50/100 profiles.
3. Native Chromium anti-detect research for canvas/audio/font/DOMRect surfaces; do not ship naive JS spoofing.
4. Final release packaging/license clearance, especially optional proprietary browser binaries.
