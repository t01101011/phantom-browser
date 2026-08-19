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

### Item 6 — Launch-contract tests (recommended first)

Assert every intended `FingerprintConfig` field is either applied natively, applied through an explicitly weaker fallback, or reported unsupported. Currently no test covers this end-to-end.

Files to touch:
- New: `apps/desktop/src/main/launchContract.test.ts`
- Reference: `apps/desktop/src/main/ChromiumBrowserDriver.ts` (flag construction)
- Reference: `packages/types/src/index.ts` (`FingerprintConfig` schema)

### Item 7 — Extend browser-level probes

Harness has 11 surfaces OBSERVED. Add: `availScreen`, DPR depth, ICU locale depth, and connect probe results back to launch-config assertions.

Files to touch:
- `scripts/native-coverage/browser-probe.mjs`
- `scripts/native-coverage/evidence.mjs`

### Item 8 — Proxy-geo failure visibility

`proxyCoherence.ts` has degraded-mode handling. Need: locale mismatch visibility before launch, fail-closed for stealth profiles, explicit acceptance of degraded coherence.

Files to touch:
- `apps/desktop/src/main/proxyCoherence.ts`
- `apps/desktop/src/main/proxyCoherence.test.ts`

## Infrastructure notes

- Auto-review cron `phantom-native-engine-auto-review` (ID `537a8eceeeab`) is paused; board is closed
- Kanban board `phantom-native-engine` has 10 done cards, 0 active
- Notion task `3a9539c8-7ba9-81ff-bdce-d2e1a0150715` should be updated to Done
- Branch `audit/native-chromium-coverage` merged and can be deleted

## Compatibility boundary

Preserve `@multizen/*`, `window.multizen`, IPC/localStorage/data paths, and `.mzar`/`MZAR`; replace only user-visible branding, assets, native prompts, CI/release labels, and add neutral MIT attribution.
