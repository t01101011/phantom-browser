# Native Chromium Coverage Audit

- Date: 2026-07-26
- Branch: `audit/native-chromium-coverage`
- Baseline: `origin/master` at `bdf280fabf862aae10e3fd182f8093e7a0797b3b`

## Executive conclusion

Phantom Browser has a sound **engine adapter** for CloakBrowser, but it does not own or pin a Chromium patchset. Its native anti-detect coverage is therefore whatever the selected upstream CloakBrowser release actually implements.

The current integration is **not yet release-reproducible**:

- it queries mutable GitHub releases at first run rather than pinning an engine revision;
- it verifies a release asset against `SHA256SUMS`, but does not authenticate the published `SHA256SUMS.sig`;
- it defaults to stock Chrome for Testing (`cft`), where several fingerprint surfaces are CDP/preload overrides rather than native Chromium behavior;
- its downloader cannot fetch the latest Pro/current CloakBrowser binaries because those releases publish signed checksum manifests but no public platform archives;
- README claims describe the CloakBrowser path as if it were the unconditional product runtime, while app defaults select CFT.

So the honest product claim today is:

> Phantom Browser supports an opt-in CloakBrowser engine adapter with native fingerprint flags. Stock CFT remains the default and uses detectable CDP/JavaScript emulation for several surfaces.

It is not yet honest to claim a pinned, independently auditable, native anti-detect Chromium fork is shipped by this repository.

## Evidence boundary

This audit distinguishes three evidence classes:

1. **Phantom source evidence** — what this repository passes to the engine or overrides through CDP/preload.
2. **Upstream wrapper evidence** — public CloakBrowser README/tests/config describing intended binary behavior.
3. **Engine patch evidence** — an inspectable, pinned Chromium source diff proving implementation inside Blink/V8/net/Chromium.

The first two are present. The third is not vendored or pinned in Phantom Browser. Upstream's repository is MIT-licensed, but the checked tree is primarily wrappers, tests, download logic, and release metadata; the custom Chromium patchset is consumed as prebuilt release artifacts. Upstream marketing statements are therefore useful provenance, not independent proof of every native surface.

## Runtime and provenance

| Item | Current implementation | Classification |
|---|---|---|
| Engine selection | `BrowserEngine = "cft" | "cloakbrowser"`; default is `cft` (`packages/settings-store/src/index.ts:4-15,42-50`). | CFT default; CloakBrowser opt-in |
| Binary source | CFT official manifest or mutable `CloakHQ/CloakBrowser` GitHub releases (`apps/desktop/src/main/ChromiumBootstrap.ts:79-86,350-352,627-652`). | Unpinned upstream binary |
| Integrity | Published SHA-256 is checked when `SHA256SUMS` exists (`ChromiumBootstrap.ts:215-221,627-652,785-797`). | Integrity only, not publisher authenticity |
| Signature | Upstream releases publish `SHA256SUMS.sig`; Phantom does not fetch or verify it. | Gap |
| Reproducibility | First compatible release is chosen newest-to-oldest; no allowlisted tag, patch commit, or archive digest lives in repo. | Gap |
| Current-release access | Current Pro tags expose checksum/signature assets but platform archives are license-gated; downloader skips them and falls back to older public v146/v145 assets. | Material drift |
| Patch ownership | No Chromium source tree or patch series is tracked by Phantom. | Upstream-dependent |
| License | Upstream repository `LICENSE` is MIT; Phantom app is MIT. Binary/service terms still need release counsel because current builds are distributed through upstream's license-gated channel. | Legal gate remains |

## Surface coverage matrix

Legend:

- **Native/upstream** — Phantom routes a native `--fingerprint-*` control into CloakBrowser and deliberately avoids JS/CDP double patching.
- **CDP/flag** — stock Chromium flag or DevTools emulation; useful baseline, but observable as automation/emulation behavior.
- **Preload JS** — page-realm JavaScript monkey patch; weakest tier.
- **Uncovered / not proven** — absent from Phantom's schema/adapter, or only claimed by upstream without a pinned engine patch proving it.

| Surface | CloakBrowser path in Phantom | CFT path in Phantom | Audit result |
|---|---|---|---|
| Canvas | Stable native seed via `--fingerprint=<seed>` (`ChromiumBrowserDriver.ts:1022-1025,1084-1092`). No Phantom canvas JS patch. | No canvas mitigation. | Native/upstream on CloakBrowser; uncovered on CFT. Exact algorithm is upstream-binary dependent. |
| AudioContext | Same seed is intended to drive native audio noise (`packages/types/src/index.ts:107-112`); no separate Phantom control. | No audio mitigation. | Native/upstream claim only on CloakBrowser; uncovered on CFT. |
| WebGL/GPU identity | Native GPU vendor/renderer flags (`ChromiumBrowserDriver.ts:1037-1042`); Phantom skips preload on CloakBrowser (`:496-504`). | JS wraps WebGL getters through preload (`:904-1011`). | Native/upstream vs detectable preload JS. |
| Fonts | No font list/pack exists in `FingerprintConfig` (`packages/types/src/index.ts:63-113`) and no Phantom font loader is wired. | None. | Upstream default may normalize fonts, but per-profile font coherence is not controlled or proven. |
| DOMRect/layout geometry | No Phantom schema, flag, CDP command, or preload implementation found. | None. | Uncovered / upstream default only. |
| Screen width/height | Native `--fingerprint-screen-*` (`ChromiumBrowserDriver.ts:1031-1033`); CDP metrics deliberately skipped (`:547-555`). | `--window-size` plus `Emulation.setDeviceMetricsOverride` (`:294-295,555-565`). | Native/upstream vs CDP emulation. |
| Available screen/work area | `availScreen` exists in schema but is not sent by the CloakBrowser adapter. | Device metrics set only full screen width/height. | Uncovered/incomplete. |
| Device pixel ratio | Profile stores `dpr`, but CloakBrowser args do not send it. | CDP `deviceScaleFactor`. | Native behavior not controlled; CFT is CDP. |
| CPU/RAM | Native `--fingerprint-hardware-concurrency` and quantized `--fingerprint-device-memory` (`:1034-1035,1069-1082`). | Navigator getters patched in preload (`:496-504,904-1011`). | Native/upstream vs preload JS. |
| Platform / cross-OS persona | Native `--fingerprint-platform` (`:1025,1095-1104`); Phantom trusts CloakBrowser for V8/CSS/Blink coherence (`:135-147`). | Persona is snapped back to host family (`:135-147`) and navigator platform is preload-patched. | Native/upstream on CloakBrowser; intentionally limited on CFT. |
| UA and Client Hints | Native brand/platform version flags (`:1043-1050`); CDP UA override skipped. | CLI UA then `Emulation.setUserAgentOverride` with metadata (`:311-315,598-607`). | Native/upstream vs CDP. |
| Timezone | Native `--fingerprint-timezone` (`:1031`). | `Emulation.setTimezoneOverride` (`:579-586`). | Native/upstream vs CDP. |
| Locale / ICU | CloakBrowser has no verified native locale flag; Phantom uses `Emulation.setLocaleOverride` (`:611-631`). | Same CDP override, plus stock `--lang`/`--accept-lang`. | CDP on both; explicitly not fully native. |
| Languages / Accept-Language | Stock `--accept-lang` for both engines (`:257-263,290-295`). | Same. | Chromium flag, not an anti-detect source patch. |
| Geolocation | Native `--fingerprint-location` only when proxy probe returns coordinates (`:175-193,305-310`). | No `Emulation.setGeolocationOverride` found. | Native/upstream on CloakBrowser with successful probe; uncovered on CFT. |
| WebRTC | Native `--fingerprint-webrtc-ip=auto` with proxy (`:302-304`); Phantom skips JS preload (`:485-504`). | Policy flags plus injected ICE spoof/block script (`:334-343,485-527`). | Native/upstream vs flag + preload JS. |
| Proxy DNS | Local SOCKS5 bridge and remote resolution; background/DoH/prefetch features disabled (`:323-374`). | Same. | Strong application/network configuration, but residual behavior is not proven by a Chromium net patch. |
| TLS JA3/JA4 | No per-profile adapter control. README puts custom spoofing in a future `multizen-pro` roadmap (`README.md:222-227`). Upstream current binary claims stock-Chrome-equivalent TLS. | Vanilla CFT TLS fingerprint. | No custom spoofing; native stock-equivalence depends entirely on upstream binary. |
| HTTP/2 SETTINGS / HTTP/3 | No adapter control or owned patch. README lists HTTP/2 fingerprinting as future work (`README.md:222-227`). | Stock engine behavior. | Uncovered as configurable persona surface. |
| CDP automation traces | Phantom avoids risky `Runtime.enable`/`Network.enable` on CloakBrowser through the CDP safety layer (`packages/cdp-driver/src/CdpSession.ts:47-51,399-403`). | Normal CDP behavior. | Good integration hardening; final stealth still depends on upstream engine. |

## Material inconsistencies found

### 1. README overstates the default runtime

`README.md:101-120,187-190` describes a patched, open-source CloakBrowser engine as the product runtime. Actual default is CFT (`packages/settings-store/src/index.ts:42-50`). This matters because CFT has no Canvas/Audio mitigation and uses CDP/preload overrides for WebGL, platform, RAM/CPU, screen, UA-CH, locale, timezone, and WebRTC.

### 2. Source comments contradict current implementation

`packages/profile-manager/src/fingerprint.ts:22-27` says Client Hints need a closed-source future binary, while `ChromiumBrowserDriver.ts:598-607` applies UA metadata through CDP and the CloakBrowser adapter sends native brand/platform-version flags. The comment is stale and should not be used as architecture truth.

Likewise `ChromiumBrowserDriver.ts:399-409` says Client Hints are not overridable via CLI and require `multizen-pro`, but the same file later applies `Emulation.setUserAgentOverride.userAgentMetadata` on CFT and native brand controls on CloakBrowser. The real distinction is not “impossible,” but “CDP-emulated on CFT vs engine-native on CloakBrowser.”

### 3. Locale is not native on CloakBrowser

The implementation documents and handles this honestly at `ChromiumBrowserDriver.ts:611-631`: there is no verified CloakBrowser locale switch, so ICU locale is filled through CDP. Product-level claims should not call the whole fingerprint native.

### 4. Upstream release channel drift

The bootstrap assumes public per-platform GitHub assets (`ChromiumBootstrap.ts:82-86,627-652`). Current upstream Pro releases publish checksum/signature manifests on GitHub while actual archives are license-gated; public archives remain on older v146/v145 tags. Phantom therefore cannot silently inherit the current 71-patch Chromium 150 build with its existing direct-download logic.

### 5. Signature downgrade

Upstream documents Ed25519 verification of signed checksum manifests. Phantom only parses a plaintext SHA-256 and ignores `SHA256SUMS.sig`. A compromised release account/CDN path could replace both archive and checksum. Pinning a digest helps reproducibility; verifying a pinned publisher key adds authenticity.

## Recommendation

### Near-term: keep CloakBrowser as an explicit adapter, but make it reproducible

1. Add a tracked engine lock manifest per platform: exact upstream tag, archive filename, SHA-256, upstream wrapper commit, Chromium version, license/channel, and feature set.
2. Verify `SHA256SUMS.sig` against a pinned Ed25519 public key before trusting checksums.
3. Fail closed when a locked platform artifact is unavailable; do not silently walk back to an older release.
4. Surface the actual resolved engine/tag/version in Settings and diagnostics.
5. Correct README/runtime copy: CFT is baseline; native coverage exists only when the opt-in CloakBrowser engine is installed and selected.
6. Add launch-contract tests that assert every intended `FingerprintConfig` field is either applied natively, applied through an explicitly weaker fallback, or reported unsupported.
7. Add browser-level probes for Canvas, Audio, WebGL, UA-CH high entropy, screen/availScreen/DPR, ICU locale, WebRTC, geolocation, DNS, and network fingerprints. A stored field or launch flag is not proof that the page observes a coherent value.

### Strategic fork decision

Do **not** start a full Chromium fork merely to close one or two UI-facing gaps. First require a pinned CloakBrowser build and exercise the real binary. Fork only if one of these remains a product requirement that upstream cannot expose or verify:

- deterministic per-profile fonts and DOMRect geometry;
- native ICU locale/languages without CDP;
- coherent screen work area and DPR controls;
- per-persona TLS/JA3/JA4, HTTP/2 SETTINGS, and HTTP/3/QUIC fingerprints;
- a redistributable, independently buildable engine with owned patch provenance.

If those are mandatory, Phantom needs an owned Chromium patchset and reproducible build pipeline. Otherwise, carrying Chromium rebases and security patches is a very expensive way to avoid maintaining a narrow upstream adapter.

## Verification performed

- Inspected Phantom Browser branch/status and source paths listed above.
- Cloned upstream `CloakHQ/CloakBrowser` at `a5f2c33ff9aa27cabd93871d714ee1469fb8fcc5` (`v0.5.2`, 2026-07-25) for wrapper/config/test and license inspection.
- Queried current upstream GitHub release metadata and compared public platform assets with Pro/current tags.
- This was a source/provenance audit only. No anti-bot benchmark was run, and no score is claimed.
