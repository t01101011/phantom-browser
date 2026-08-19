# Phantom Browser — Active Handoff

Canonical historical roadmap: `/root/projects/phantom-browser/PLAN.md`

Current canonical repository: `https://github.com/t01101011/phantom-browser`

## Current milestone: Native Chromium coverage hardening — COMPLETE (2026-08-19)

PR #11 merged to master at `ae1fc81`. All 10 Kanban cards done. Board `phantom-native-engine` closed.

### Verified evidence

- Source HEAD: `ae1fc81c6879f3c84dce9ba3d3524f28f5c9de29` (merge commit)
- Audit HEAD: `e721ebbbea7a4affe642893701f08ccf10f9f99b`
- Policy commit: `6c74974f9fa7432f956b681236adad8efaae4f7c`
- Independent review PASS: patch digest `f635427d2c759ee5b5b977ec7ca0f3c46647dcf01e635bb2e010642b312f7689`
- 54/54 tests PASS, 11/11 coverage tests PASS, typecheck/lint/build PASS
- CFT binary SHA-256: `b73b9e817990d5d6e6167e1011dadb4b53f7e37392fc658f1e809df07ea6b2b7`
- Windows proof: real win32/x64, Chrome 151, residential proxy VNPT exit IP 222.252.4.188
- 100% visual SHA-256: `a1621187342b78ec8c9ce3b6c598368022a9ae7a916159ed4484f7e805a4aa56`
- 125% visual SHA-256: `b6b7f5dcedabff765223b4fdc883d8abd2b28cfc430c78639b2b157d2b7a924f`

### Strategy decided: Option B

- CFT is the sole production baseline and redistributable runtime
- CloakBrowser remains opt-in evaluation only; no bundling/redistribution without written rights
- No Chromium fork authorized
- Canonical record: `NATIVE_CHROMIUM_COVERAGE_AUDIT.md` and `docs/audits/native-chromium-coverage.md`

### Completed audit items (1-5, 9)

1. Engine lock manifest per platform — done (`cloakbrowser-engine-lock.json`)
2. Ed25519 signature verification — done (`cloakBrowserArtifactLock.ts`)
3. Fail closed on unavailable locked artifact — done
4. Surface resolved engine/tag/version in Settings — done
5. Correct README/runtime copy — done
9. Conservative product policy — done (CFT-only, CloakBrowser non-distributable)

## Next implementation slice

### Item 6 — Launch-contract tests — COMPLETE (2026-08-19)

Created `apps/desktop/src/main/launchContract.ts` (pure module extracted from `ChromiumBrowserDriver.ts`) and `apps/desktop/src/main/launchContract.test.ts` (21 tests).

The contract maps every `FingerprintConfig` field to its coverage level per engine:
- **native-flag** — CloakBrowser `--fingerprint-*` CLI arg (C++ level)
- **cli-flag** — stock Chromium `--` CLI arg
- **cdp** — CDP `Emulation.*` (weaker than native, potentially observable)
- **preload-js** — `Page.addScriptToEvaluateOnNewDocument` (JS override)
- **unsupported** — documented as not applied

Key findings encoded in the contract:
- CloakBrowser has no native locale switch — CDP `setLocaleOverride` fills the gap (not a double-patch)
- `clientHints.secChUaArch/Bitness/Mobile/Model` are CDP-only on CFT, unsupported on CloakBrowser
- `country` is not a browser fingerprint surface (GUI/proxy-coherence only)
- `seed` is CloakBrowser-only (canvas/audio/WebGL readback noise)
- No field uses preload-js on CloakBrowser (would create double-spoof anomalies)

Verification: 21/21 new tests pass, 75/75 full suite pass, typecheck clean.

### Item 7 — Extend browser-level probes — COMPLETE (2026-08-19)

Extended the native-coverage harness from 11 to 14 observed surfaces:

1. **`availScreen`** — `screen.availLeft`/`availTop` + taskbar deduction. Dedicated probe for the available-screen surface that CFT patches via preload-js but CloakBrowser leaves unsupported (`availLeft`/`availTop` are NOT patched on either engine).

2. **`dprDepth`** — `devicePixelRatio` quantization (integer vs fractional), `matchMedia(resolution: Ndppx)` queries for 1/1.25/1.5/1.75/2/2.5/3. Fractional DPR is a host-OS tell (Windows DPI scaling).

3. **`icuLocale`** — deep ICU locale probing: `calendar`, `numberingSystem`, `hourCycle`, `timeZoneName` from `DateTimeFormat/NumberFormat/Locale/ListFormat/PluralRules/Collator`. These are V8 ICU data, NOT controllable via `--lang`/`--accept-lang` flags. Connects to the Item 6 contract finding that locale is the only CloakBrowser field using CDP.

**Probe-to-contract cross-reference:** created `launchContractProbe.ts` + test (16 tests) that maps each new probe surface to its `FingerprintConfig` field and assert the coverage level matches the launch contract:
- `availScreen` → CFT: preload-js, CloakBrowser: unsupported
- `dprDepth` → CFT: cdp, CloakBrowser: unsupported
- `icuLocale` → CFT: cdp, CloakBrowser: cdp (the documented gap)

Verification: 95/95 full suite pass (20 new), typecheck clean.

### Item 8 — Proxy-geo failure visibility — COMPLETE (2026-08-19)

Extended `proxyCoherence.ts` with structured pre-launch visibility, fail-closed for stealth engines, and explicit degraded acceptance.

**New API:**
- `recommendedAction: "launch" | "accept-degraded" | "fail-closed"` on every `ProxyCoherenceResult`
- `precheckProxyCoherence()` — probes proxy geo and resolves coherence WITHOUT spawning a browser; GUI calls this before Launch to surface issues
- `canLaunchWithCoherence(result, acceptDegraded)` — gate function for the launch path
- `summarizeCoherenceIssues(result)` — human-readable string for UI dialogs/banners

**Decision matrix:**
| Issue | CFT | CloakBrowser |
|---|---|---|
| No issues | launch | launch |
| Locale mismatch | accept-degraded (throws without acceptDegraded) | fail-closed |
| Probe timeout/fail | accept-degraded | fail-closed |
| Missing coords | accept-degraded | fail-closed |
| Invalid egress IP | fail-closed | fail-closed |

Key behavioral change: CFT with invalid egress IP is now `fail-closed` (was silently degraded). WebRTC spoofing can't work without a valid egress IP, so proceeding would create an active leak.

Verification: 110/110 full suite pass (15 new tests), typecheck clean.

## Infrastructure notes

- Auto-review cron `phantom-native-engine-auto-review` (ID `537a8eceeeab`) is paused; board is closed
- Kanban board `phantom-native-engine` has 10 done cards, 0 active
- Notion task `3a9539c8-7ba9-81ff-bdce-d2e1a0150715` should be updated to Done
- Branch `audit/native-chromium-coverage` merged and can be deleted

## Compatibility boundary

Preserve `@multizen/*`, `window.multizen`, IPC/localStorage/data paths, and `.mzar`/`MZAR`; replace only user-visible branding, assets, native prompts, CI/release labels, and add neutral MIT attribution.
