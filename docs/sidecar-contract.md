# Phantom Sidecar — JSON-RPC Contract (v1)

> Stable contract between the Tauri Rust shell and the Python backend.
> Rust spawns the sidecar and reads exactly ONE JSON object per call from stdout.
> stderr is diagnostic logs only — never parsed.

## Invocation

**Dev:**
```bash
cd /root/projects/phantom-browser && set -a && . .env && set +a
.venv/bin/python -m phantom.sidecar <action> [--args...]
```

**Ship (Windows):** `phantom-sidecar.exe <action> ...` (bundled via PyInstaller — TODO Phase 2 ship).

Env: must export `PROXY_1_USER`, `PROXY_1_PASS`, ... from `.env` BEFORE spawning.
Rust does this by either: (a) running `set -a && . .env && set +a` before the sidecar (on Linux dev), or (b) loading `.env` itself and passing `env:` to `Command::new()`.

## Envelope

Every response (success or logical failure) is ONE JSON object on stdout:

```json
// success
{"ok": true, "data": { ... per-action ... }}

// logical failure (still exit 0)
{"ok": false, "error": {"code": "string", "message": "...", "detail": null | "traceback" | ...}}
```

**Exit code** is 0 even on logical errors — so Rust can `serde_json`-parse stdout without
special-casing. Only a stdlib crash (argparse panic, OOM, SIGSEGV) → non-zero, and Rust
must still attempt to read stdout for an envelope.

## Actions

### `list [--platform p]`
```json
{"profiles": [ProfilePublic, ...], "count": N}
```

### `get <id|name>`
```json
ProfilePublic
```

### `create --name N --platform P --proxy H:P:U:PW [--tz TZ] [--notes T]`
```json
{"profile": ProfilePublic, "duplicate_proxy_count": N}
```
`duplicate_proxy_count > 0` → GUI shows a warning (does not block).

### `launch <id|name> [--url U] [--headless H]`
- `--headless` values: `"virtual"` (default, Xvfb — Linux dev), `"true"`, `"false"`.
- On Windows ship: GUI passes `--headless false` (real browser window, tk logs in by hand).
```json
{"profile_id": 1, "pid": 12345, "log_path": ".../<platform-data-dir>/profiles/profile_1/launcher.log"}
```

### `stop <id|name>`
```json
{"profile_id": 1, "stopped": true, "previous_pid": 12345}
```
`stopped: false` means it wasn't running. `previous_pid` is null if not running.

### `delete <id|name>`
Refuses with error `code: "still_running"` if browser is running.
```json
{"profile_id": 1, "deleted": true}
```

### `status <id|name>`
```json
{"profile_id": 1, "status": "idle"|"running", "running": bool, "pid": 12345|null, "log_path": "..."|null}
```

### `log-tail <id|name> [--bytes N]`
Default 8KB, clamps 64B .. 1MB. Cuts the leading partial line when reading from middle-of-file.
```json
{"profile_id": 1, "bytes": 4096, "log": "..."}
```

### `presets`
```json
{"presets": {"facebook": {...}, "tiktok": {...}, "chatgpt": {...}, "custom": {...}}}
```
Returns the full `presets.PRESETS` dict — see `src/phantom/presets.py`.

## ProfilePublic (shared shape)

Fields exposed to the GUI:

| Field | Type | Notes |
|---|---|---|
| `id` | int | |
| `name` | str | unique |
| `platform_tag` | str | facebook/tiktok/chatgpt/custom |
| `status` | str | "idle" \| "running" |
| `proxy_host` | str | |
| `proxy_port` | int | |
| `proxy_user` | str | (visible — needed for display; proxy_pass is NOT) |
| `proxy_source` | str | "manual" \| "iproyal" \| "file" |
| `target_os` | str | "windows" default |
| `timezone` | str\|null | |
| `locale_language` | str | "en" |
| `locale_region` | str | "US" |
| `navigator_language` | str | "en-US" |
| `user_data_dir` | str | |
| `notes` | str | |
| `created_at` | str | ISO |
| `updated_at` | str | ISO |

**Secret / blob fields NEVER exposed:** `proxy_pass`, `fingerprint_json`, `seeds_json`,
`webgl_json`, `fonts_json`, `voices_json`, `misc_json`. If GUI needs to display
fingerprint detail, add a separate `fingerprint-summary <id>` action later.

## Error codes (stable, Rust matches on these)

| Code | Meaning | HTTP-ish analog |
|---|---|---|
| `bad_args` | argparse rejected the args | 400 |
| `not_found` | profile id/name doesn't exist | 404 |
| `bad_proxy` | `--proxy` not in `host:port:user:pass` form | 400 |
| `already_running` | launch attempted while browser already running | 409 |
| `still_running` | delete attempted while browser running (must stop first) | 409 |
| `no_log` | log-tail requested but launcher.log doesn't exist yet | 404 |
| `panic` | uncaught Python exception (look at `detail` for traceback) | 500 |

## Polling pattern (Phase 2 GUI)

```
on launch click  →  sidecar launch <id>
                  → store returned pid in React state
                  → begin log-tail poll every 1000ms: sidecar log-tail <id>
                  → on each tick: sidecar status <id> to detect death
                  → stop polling when status.running == false
on stop click    →  sidecar stop <id>
                  → stop log-tail poll, fetch final log-tail for display
```

## Why a separate `sidecar.py` instead of `cli.py --json`

- `cli.py` is tk's human CLI: tui tables, `[+]` prefixes, `sys.exit()` on errors.
  Mixing JSON in there risks breaking the terminal UX that already works.
- `sidecar.py` is JSON-only from the ground up: never `print`s anything non-JSON,
  never `sys.exit`s non-zero except on a stdlib crash.
- One file = easy to replace later with a PyInstaller-bundled standalone for ship,
  without touching the human CLI.
