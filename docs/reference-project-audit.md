# Phantom Browser — reference project audit

Date: 2026-07-19

## Primary reference: FoxDesk

- Repo: https://github.com/BB0813/foxdesk
- License: MIT
- Stack: Python/FastAPI + pywebview/WebView2 + native HTML/CSS/JS + Camoufox
- Packaging: PyInstaller + Inno Setup, built on GitHub Actions `windows-latest`
- Latest verified release during audit: v1.4.0, with Windows Setup EXE, portable ZIP, and SHA256SUMS
- Evidence in source: `foxdesk.spec`, `installer.iss`, `build.bat`, `.github/workflows/build.yml`, 58 pytest test functions

Why it is the closest benchmark: it solves the same product boundary as Phantom Browser — local Windows profile manager around Camoufox — and has actually shipped Windows artifacts. Its desktop launcher starts a localhost FastAPI server, waits until ready, then opens it through pywebview. The frozen EXE also dispatches browser workers, avoiding a separately installed Python sidecar.

Patterns to adopt:

1. Build Windows on `windows-latest`, not Linux cross-compile.
2. Package Python runtime/backend and worker into the release artifact.
3. Use readiness probing before opening WebView2.
4. Treat desktop shell, server, and browser worker as explicit process modes of one frozen executable.
5. Produce both portable ZIP and installer, plus checksums.
6. Test process/session lifecycle and packaging paths in CI.

## Secondary reference: Mirage Browser

- Repo: https://github.com/taills/Mirage-Browser
- License: MIT
- Stack: Electron + TypeScript + Vite + Chrome CDP + Mihomo
- Latest verified release during audit: v0.0.2 with 8 release assets for Windows/macOS/Linux

Useful for UX and shipping: environment/profile list, per-profile proxy and fingerprint form, multi-platform Electron Forge packaging, release workflow. Do not copy its fingerprint engine as the security baseline: it overrides values through CDP/script injection rather than Camoufox's engine-level patching.

## Other candidates

- https://github.com/feder-cr/firefox_antidetect — relevant patched-Firefox + pywebview manager, MIT, process tracking via psutil; very new and no verified release artifact during audit.
- https://github.com/potionxyz/veilbrowse — Electron/Express/SQLite profile manager with a Linux release; fingerprint spoofing is init-script based and the project is Linux-focused.
- https://github.com/botzvn/browser-manager — polished self-hosted web architecture, but young, no declared license/release during audit and not a close Windows desktop reference.

## Decision

Keep Phantom's Camoufox identity/persistence work. Reconsider the Tauri + externally provisioned Python sidecar release architecture. The next implementation pass should first reproduce FoxDesk's Windows-native packaging pipeline, then compare whether adapting/forking FoxDesk is cheaper and safer than continuing the custom shell.
