<div align="center">
  <img src=".github/assets/logo.png" width="96" height="96" alt="Phantom Browser" />

  <h1>Phantom Browser</h1>

  <p><strong>AI-native antidetect browser with persistent Chromium profiles.</strong></p>

  <p>
    Local Chromium profiles with their own cookies, fingerprint, and proxy.<br/>
    Drive them through MCP from Cursor, Claude Desktop, or any MCP client.<br/>
    Step in manually whenever the agent hits a CAPTCHA or 2FA prompt.
  </p>

  <p>
    <a href="https://github.com/t01101011/phantom-browser/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/t01101011/phantom-browser?style=for-the-badge&color=42F58D&labelColor=0a0b0f"></a>
    <a href="https://github.com/t01101011/phantom-browser/blob/master/LICENSE"><img alt="MIT License" src="https://img.shields.io/github/license/t01101011/phantom-browser?style=for-the-badge&color=42F58D&labelColor=0a0b0f"></a>
    <a href="https://github.com/t01101011/phantom-browser/actions/workflows/release.yml"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/t01101011/phantom-browser/release.yml?style=for-the-badge&labelColor=0a0b0f"></a>
    <a href="https://github.com/t01101011/phantom-browser/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/t01101011/phantom-browser/total?style=for-the-badge&color=42F58D&labelColor=0a0b0f"></a>
  </p>

  <p>
    <a href="https://github.com/t01101011/phantom-browser/releases/latest"><strong>Download</strong></a>
  </p>
</div>

---

## What is Phantom Browser?

Phantom Browser is a desktop app that runs a library of isolated Chromium browser profiles. Each profile has its own cookies, login state, fingerprint, and proxy. A local MCP server on `127.0.0.1:7777` exposes browser-drive tools (navigate, click, type, extract, screenshot) to any MCP client.

This is a fork of [MultiZen](https://github.com/multizenteam/multizen-browser) (MIT-licensed) with independent branding, design system, and feature work. The upstream MIT license and attribution are preserved.

### Key features

- **Persistent profiles** — each profile has its own user-data directory, cookies, localStorage, IndexedDB, and extension set
- **Per-profile proxy** — HTTP/SOCKS5 proxy with DNS-over-proxy and WebRTC leak prevention
- **Fingerprint management** — coherent fingerprints via Chrome for Testing (CFT) or CloakBrowser (opt-in evaluation)
- **MCP server** — drive profiles from Cursor, Claude Desktop, or any MCP-compatible client
- **Companion extension** — "Add to Phantom Browser" button on Chrome Web Store pages
- **Encrypted archive export** — `.mzar` encrypted profile archives for backup/transfer
- **Profile groups** — tag-based grouping with bulk launch/stop
- **Dark UI** — near-black surfaces with restrained spectral-green accents

## Download

### Windows

Download [Phantom-Browser-win-x64.exe](https://github.com/t01101011/phantom-browser/releases/latest/download/Phantom-Browser-win-x64.exe). SmartScreen may flag the installer as unrecognized on first download. Click **More info**, then **Run anyway**.

### macOS (Apple Silicon)

Download [Phantom-Browser-mac-arm64.dmg](https://github.com/t01101011/phantom-browser/releases/latest/download/Phantom-Browser-mac-arm64.dmg). Since the app is unsigned, run this once after install:

```bash
xattr -cr /Applications/Phantom\ Browser.app
```

### macOS (Intel)

Download [Phantom-Browser-mac-x64.dmg](https://github.com/t01101011/phantom-browser/releases/latest/download/Phantom-Browser-mac-x64.dmg). Same quarantine bypass as above.

### Linux

```bash
curl -LO https://github.com/t01101011/phantom-browser/releases/latest/download/Phantom-Browser-linux-x86_64.AppImage
chmod +x Phantom-Browser-linux-x86_64.AppImage
./Phantom-Browser-linux-x86_64.AppImage
```

## How it works

```
  Cursor / Claude Desktop  ──MCP──►  Phantom Browser Desktop App
                                           │
                                           ├──► SQLite (profiles.db)
                                           │
                                           └──► Chromium (per-profile user-data-dir + proxy + fingerprint)
```

| Component | Tech |
|---|---|
| Desktop shell | Electron + React |
| Profile store | SQLite (better-sqlite3) |
| Browser engine | Chrome for Testing (default), CloakBrowser (opt-in) |
| MCP transport | stdio + HTTP (SSE) |
| IPC | Electron ipcMain/ipcRenderer + `window.multizen` bridge |

## MCP configuration

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "phantom": {
      "command": "npx",
      "args": ["-y", "@multizen/mcp-server"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "phantom": {
      "command": "npx",
      "args": ["-y", "@multizen/mcp-server"]
    }
  }
}
```

## Development

```bash
git clone https://github.com/t01101011/phantom-browser
cd phantom-browser
yarn install
yarn dev
```

### Build

```bash
yarn build          # typecheck + vite build + electron-builder
yarn test           # 110 tests
yarn typecheck      # workspace-wide
yarn lint           # workspace-wide
```

### Native Chromium coverage

Phantom Browser includes a native Chromium coverage audit that maps every `FingerprintConfig` field to its coverage level per engine:

| Level | Meaning |
|---|---|
| **native-flag** | C++ level via CloakBrowser `--fingerprint-*` CLI args |
| **cli-flag** | Stock Chromium `--` CLI arg |
| **cdp** | CDP `Emulation.*` (weaker than native, potentially observable) |
| **preload-js** | `Page.addScriptToEvaluateOnNewDocument` (JS override) |
| **unsupported** | Not applied |

See `NATIVE_CHROMIUM_COVERAGE_AUDIT.md` and `docs/audits/native-chromium-coverage.md` for the full audit results.

## Licensing

| Layer | License |
|---|---|
| App source (this repo) | MIT |
| MCP server + CDP driver + profile manager | MIT |
| Chrome for Testing (CFT) | Google ToS — redistributable |
| CloakBrowser compiled binary | Proprietary — **not bundled/redistributed** without written OEM permission |

This project is a fork of [MultiZen](https://github.com/multizenteam/multizen-browser) (MIT). The upstream license and attribution are preserved. Third-party notices are in `THIRD_PARTY_NOTICES.txt`.

## Acknowledgements

- [MultiZen](https://github.com/multizenteam/multizen-browser) — the upstream project this fork is based on
- [Electron](https://www.electronjs.org/) — cross-platform desktop framework
- [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) — standalone Chromium for automation
