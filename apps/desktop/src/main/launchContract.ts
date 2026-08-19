/**
 * Launch contract — pure functions that translate a {@link FingerprintConfig}
 * into the concrete launch artifacts (CLI args, CDP calls, preload scripts).
 *
 * Extracted from ChromiumBrowserDriver.ts so they can be unit-tested without
 * pulling in `electron`.
 *
 * The contract is: every field in `FingerprintConfig` MUST appear in the
 * coverage map returned by {@link describeLaunchContract}, classified as one
 * of:
 *   - "native-flag"   — applied via a CloakBrowser `--fingerprint-*` CLI arg
 *   - "cli-flag"      — applied via a stock Chromium `--` CLI arg
 *   - "cdp"           — applied via CDP `Emulation.*` (weaker than native)
 *   - "preload-js"   — applied via `Page.addScriptToEvaluateOnNewDocument`
 *   - "unsupported"   — documented as not applied on this engine
 */

import { createHash } from "node:crypto";
import type { ClientHints, FingerprintConfig, ProfileId } from "@multizen/types";
import type { BrowserEngine } from "@multizen/settings-store";

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * The value a real browser reports for `navigator.deviceMemory` / the
 * `Sec-CH-Device-Memory` hint: physical RAM rounded to the NEAREST power of two
 * and CAPPED AT 8 — the Device Memory API's spec upper bound. Chrome computes
 * `2 ** round(log2(gb))` clamped to [0.25, 8] (Blink's `floor(log2+0.5)`), so it
 * never exposes a value above 8; emitting a persona's raw physical RAM
 * (16/18/32/64 GB) would be an instant, impossible-value bot tell. The
 * fingerprint keeps the physical value for the UI and persona coherence; only
 * the web-facing surfaces get this quantized value.
 */
export function deviceMemoryApiValue(physicalGb: number): number {
  if (!(physicalGb > 0)) return 8;
  return Math.min(8, 2 ** Math.round(Math.log2(physicalGb)));
}

export function fingerprintSeed(profileId: ProfileId, fp: FingerprintConfig): string {
  const material = fp.seed ?? profileId;
  const hex = createHash("sha256").update(material).digest("hex").slice(0, 8);
  return String(10000 + (Number.parseInt(hex, 16) % 90000));
}

export function cloakBrowserPlatform(
  fp: FingerprintConfig,
): "macos" | "windows" | "linux" {
  if (fp.device.startsWith("mac") || fp.device.startsWith("imac")) return "macos";
  if (fp.device.startsWith("windows")) return "windows";
  if (fp.device.startsWith("linux")) return "linux";
  if (process.platform === "darwin") return "macos";
  if (process.platform === "win32") return "windows";
  return "linux";
}

export function primaryBrandVersion(ch: ClientHints | undefined): string | null {
  if (!ch?.secChUaFullVersionList) return null;
  const matches = ch.secChUaFullVersionList.matchAll(/"([^"]+)";v="([^"]+)"/g);
  for (const m of matches) {
    const brand = m[1];
    const version = m[2];
    if (!brand || !version) continue;
    if (!/Chromium|Not[.\s/]?A[.\s/]?Brand/i.test(brand)) return version;
  }
  return null;
}

// ── CDP UA metadata ────────────────────────────────────────────────────────

export function parseBrandList(
  header: string,
): Array<{ brand: string; version: string }> {
  const out: Array<{ brand: string; version: string }> = [];
  for (const part of header.split(",")) {
    const m = part.trim().match(/^"([^"]*)"\s*;\s*v="([^"]*)"\s*$/);
    if (!m || m[1] === undefined || m[2] === undefined) continue;
    out.push({ brand: m[1], version: m[2] });
  }
  return out;
}

export function buildUserAgentMetadata(fp: FingerprintConfig): {
  brands: Array<{ brand: string; version: string }>;
  fullVersionList: Array<{ brand: string; version: string }>;
  platform: string;
  platformVersion: string;
  architecture: string;
  bitness: string;
  model: string;
  mobile: boolean;
  wow64: boolean;
} {
  const ch: ClientHints = fp.clientHints;
  return {
    brands: parseBrandList(ch.secChUa),
    fullVersionList: parseBrandList(ch.secChUaFullVersionList),
    platform: ch.secChUaPlatform,
    platformVersion: ch.secChUaPlatformVersion,
    architecture: ch.secChUaArch,
    bitness: ch.secChUaBitness,
    model: ch.secChUaModel,
    mobile: ch.secChUaMobile === "?1",
    wow64: false,
  };
}

export function safeBuildUserAgentMetadata(
  fp: FingerprintConfig,
): ReturnType<typeof buildUserAgentMetadata> | null {
  if (!fp.clientHints || !fp.clientHints.secChUa) return null;
  try {
    return buildUserAgentMetadata(fp);
  } catch {
    return null;
  }
}

// ── CloakBrowser native CLI args ───────────────────────────────────────────

export function buildCloakBrowserFingerprintArgs(
  profileId: ProfileId,
  fp: FingerprintConfig,
): string[] {
  const args = [
    `--fingerprint=${fingerprintSeed(profileId, fp)}`,
    `--fingerprint-platform=${cloakBrowserPlatform(fp)}`,
    `--fingerprint-timezone=${fp.timezone}`,
    `--fingerprint-screen-width=${fp.screen.width}`,
    `--fingerprint-screen-height=${fp.screen.height}`,
    `--fingerprint-hardware-concurrency=${fp.hardwareConcurrency}`,
    `--fingerprint-device-memory=${deviceMemoryApiValue(fp.deviceMemory)}`,
  ];
  if (fp.webgl?.vendor) args.push(`--fingerprint-gpu-vendor=${fp.webgl.vendor}`);
  if (fp.webgl?.renderer)
    args.push(`--fingerprint-gpu-renderer=${fp.webgl.renderer}`);
  const brandVersion = primaryBrandVersion(fp.clientHints);
  if (brandVersion) args.push(`--fingerprint-brand-version=${brandVersion}`);
  if (fp.clientHints?.secChUaPlatformVersion) {
    args.push(
      `--fingerprint-platform-version=${fp.clientHints.secChUaPlatformVersion}`,
    );
  }
  return args;
}

// ── Fingerprint preload script (CFT) ───────────────────────────────────────

export function buildFingerprintPreloadScript(
  fp: FingerprintConfig,
  opts: { includeWebGl?: boolean } = {},
): string {
  const includeWebGl = opts.includeWebGl ?? true;
  return `
(() => {
  const INCLUDE_WEBGL = ${JSON.stringify(includeWebGl)};
  const PLATFORM = ${JSON.stringify(fp.platform)};
  const HW_CONCURRENCY = ${fp.hardwareConcurrency};
  const DEVICE_MEMORY = ${deviceMemoryApiValue(fp.deviceMemory)};
  const GPU_VENDOR = ${JSON.stringify(fp.webgl.vendor)};
  const GPU_RENDERER = ${JSON.stringify(fp.webgl.renderer)};
  const SCREEN_W = ${fp.screen.width};
  const SCREEN_H = ${fp.screen.height};
  const AVAIL_W = ${fp.availScreen?.width ?? fp.screen.width};
  const AVAIL_H = ${fp.availScreen?.height ?? fp.screen.height};
  const DPR = ${fp.dpr};

  function fakeNative(fn, name) {
    try {
      const stringified = "function " + name + "() { [native code] }";
      Object.defineProperty(fn, "toString", {
        value: function () { return stringified; },
        configurable: false,
        writable: false,
      });
      Object.defineProperty(fn, "name", { value: name });
    } catch (_) {}
  }

  function defineProp(obj, prop, value) {
    try {
      Object.defineProperty(obj, prop, {
        get: function () { return value; },
        configurable: true,
      });
    } catch (_) {}
  }

  defineProp(Navigator.prototype, "platform", PLATFORM);
  defineProp(Navigator.prototype, "hardwareConcurrency", HW_CONCURRENCY);
  defineProp(Navigator.prototype, "deviceMemory", DEVICE_MEMORY);

  defineProp(Screen.prototype, "width", SCREEN_W);
  defineProp(Screen.prototype, "height", SCREEN_H);
  defineProp(Screen.prototype, "availWidth", AVAIL_W);
  defineProp(Screen.prototype, "availHeight", AVAIL_H);
  defineProp(Screen.prototype, "colorDepth", 24);
  defineProp(Screen.prototype, "pixelDepth", 24);

  defineProp(window, "devicePixelRatio", DPR);

  const debugInfoEnabled = new WeakMap();
  function patchGetExtension(Ctor) {
    if (!Ctor || !Ctor.prototype) return;
    const origGet = Ctor.prototype.getExtension;
    if (!origGet) return;
    function wrapped(name) {
      const result = origGet.call(this, name);
      if (result && name === "WEBGL_debug_renderer_info") {
        debugInfoEnabled.set(this, true);
      }
      return result;
    }
    fakeNative(wrapped, "getExtension");
    Object.defineProperty(Ctor.prototype, "getExtension", {
      value: wrapped, configurable: true, writable: true,
    });
  }
  function patchGetParameter(Ctor) {
    if (!Ctor || !Ctor.prototype || !Ctor.prototype.getParameter) return;
    const orig = Ctor.prototype.getParameter;
    function wrapped(p) {
      if (p === 0x9245 || p === 0x9246) {
        if (!debugInfoEnabled.get(this)) {
          return orig.call(this, p);
        }
        return p === 0x9245 ? GPU_VENDOR : GPU_RENDERER;
      }
      return orig.call(this, p);
    }
    fakeNative(wrapped, "getParameter");
    Object.defineProperty(Ctor.prototype, "getParameter", {
      value: wrapped, configurable: true, writable: true,
    });
  }
  if (INCLUDE_WEBGL) {
    patchGetExtension(window.WebGLRenderingContext);
    patchGetExtension(window.WebGL2RenderingContext);
    patchGetParameter(window.WebGLRenderingContext);
    patchGetParameter(window.WebGL2RenderingContext);
  }
})();
`;
}

// ── Version reconciliation ─────────────────────────────────────────────────

export function reconcileVersionInFingerprint(
  fp: FingerprintConfig,
  actual: { major: number; full: string },
): FingerprintConfig {
  const newUA = fp.userAgent.replace(
    /Chrome\/\d+\.\d+\.\d+\.\d+/,
    `Chrome/${actual.full}`,
  );
  if (!fp.clientHints) {
    return { ...fp, userAgent: newUA };
  }
  const ch = fp.clientHints;
  const newSecChUa = ch.secChUa.replace(
    /("(?:Chromium|Google Chrome|Microsoft Edge)";v=")(\d+)(")/g,
    `$1${actual.major}$3`,
  );
  const newFullList = ch.secChUaFullVersionList.replace(
    /("(?:Chromium|Google Chrome|Microsoft Edge)";v=")[\d.]+(")/g,
    `$1${actual.full}$2`,
  );
  return {
    ...fp,
    userAgent: newUA,
    clientHints: {
      ...ch,
      secChUa: newSecChUa,
      secChUaFullVersionList: newFullList,
    },
  };
}

// ── Launch contract description ────────────────────────────────────────────

export type CoverageLevel =
  | "native-flag"
  | "cli-flag"
  | "cdp"
  | "preload-js"
  | "unsupported";

export interface FieldCoverage {
  field: string;
  cft: CoverageLevel;
  cloakbrowser: CoverageLevel;
  notes?: string;
}

/**
 * The launch contract: maps every field in {@link FingerprintConfig} to how
 * it is applied at launch time for each engine.
 *
 * This is the executable spec — if a new field is added to FingerprintConfig
 * but not wired up here, the contract test will fail.
 */
export const LAUNCH_CONTRACT: FieldCoverage[] = [
  {
    field: "device",
    cft: "cli-flag",
    cloakbrowser: "native-flag",
    notes:
      "CFT: reconciled to host via reconcileDeviceFamilyToHost. CloakBrowser: --fingerprint-platform= derived from device",
  },
  {
    field: "userAgent",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: Emulation.setUserAgentOverride. CloakBrowser: --fingerprint-brand-version= drives UA natively",
  },
  {
    field: "platform",
    cft: "preload-js",
    cloakbrowser: "native-flag",
    notes:
      "CFT: also set via Emulation.setUserAgentOverride(platform), but preload-js covers iframes/workers. CloakBrowser: --fingerprint-platform= (native C++)",
  },
  {
    field: "clientHints.secChUa",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: userAgentMetadata in Emulation.setUserAgentOverride. CloakBrowser: --fingerprint-brand-version=",
  },
  {
    field: "clientHints.secChUaPlatform",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes: "CFT: userAgentMetadata.platform. CloakBrowser: native",
  },
  {
    field: "clientHints.secChUaPlatformVersion",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: userAgentMetadata.platformVersion. CloakBrowser: --fingerprint-platform-version=",
  },
  {
    field: "clientHints.secChUaArch",
    cft: "cdp",
    cloakbrowser: "unsupported",
    notes: "CFT: userAgentMetadata.architecture. CloakBrowser: no native arch flag",
  },
  {
    field: "clientHints.secChUaBitness",
    cft: "cdp",
    cloakbrowser: "unsupported",
    notes:
      "CFT: userAgentMetadata.bitness. CloakBrowser: no native bitness flag",
  },
  {
    field: "clientHints.secChUaMobile",
    cft: "cdp",
    cloakbrowser: "unsupported",
    notes: "CFT: userAgentMetadata.mobile. CloakBrowser: no native mobile flag",
  },
  {
    field: "clientHints.secChUaModel",
    cft: "cdp",
    cloakbrowser: "unsupported",
    notes: "CFT: userAgentMetadata.model. CloakBrowser: no native model flag",
  },
  {
    field: "clientHints.secChUaFullVersionList",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: userAgentMetadata.fullVersionList. CloakBrowser: --fingerprint-brand-version=",
  },
  {
    field: "locale",
    cft: "cdp",
    cloakbrowser: "cdp",
    notes:
      "Both: --lang= CLI flag sets UI language. CFT: also Emulation.setLocaleOverride. CloakBrowser: no native locale switch, CDP fills the gap",
  },
  {
    field: "languages",
    cft: "cli-flag",
    cloakbrowser: "cli-flag",
    notes: "Both: --accept-lang= drives navigator.languages + HTTP header",
  },
  {
    field: "acceptLanguage",
    cft: "cdp",
    cloakbrowser: "cli-flag",
    notes:
      "Both: --accept-lang= plain list. CFT: also Emulation.setUserAgentOverride(acceptLanguage)",
  },
  {
    field: "timezone",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: Emulation.setTimezoneOverride. CloakBrowser: --fingerprint-timezone=",
  },
  {
    field: "country",
    cft: "unsupported",
    cloakbrowser: "unsupported",
    notes:
      "Not a browser fingerprint surface — used by GUI for flag rendering and proxy coherence, not applied at launch",
  },
  {
    field: "screen.width",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: Emulation.setDeviceMetricsOverride(screenWidth) + preload-js. CloakBrowser: --fingerprint-screen-width=",
  },
  {
    field: "screen.height",
    cft: "cdp",
    cloakbrowser: "native-flag",
    notes:
      "CFT: Emulation.setDeviceMetricsOverride(screenHeight) + preload-js. CloakBrowser: --fingerprint-screen-height=",
  },
  {
    field: "availScreen",
    cft: "preload-js",
    cloakbrowser: "unsupported",
    notes:
      "CFT: preload-js defineProp on Screen.prototype.availWidth/availHeight. CloakBrowser: no native availScreen flag",
  },
  {
    field: "dpr",
    cft: "cdp",
    cloakbrowser: "unsupported",
    notes:
      "CFT: Emulation.setDeviceMetricsOverride(deviceScaleFactor) + preload-js. CloakBrowser: no native DPR flag (screen flags imply DPR)",
  },
  {
    field: "webgl.vendor",
    cft: "preload-js",
    cloakbrowser: "native-flag",
    notes:
      "CFT: patchGetParameter on WebGLRenderingContext. CloakBrowser: --fingerprint-gpu-vendor=",
  },
  {
    field: "webgl.renderer",
    cft: "preload-js",
    cloakbrowser: "native-flag",
    notes:
      "CFT: patchGetParameter on WebGLRenderingContext. CloakBrowser: --fingerprint-gpu-renderer=",
  },
  {
    field: "hardwareConcurrency",
    cft: "preload-js",
    cloakbrowser: "native-flag",
    notes:
      "CFT: defineProp on Navigator.prototype. CloakBrowser: --fingerprint-hardware-concurrency=",
  },
  {
    field: "deviceMemory",
    cft: "preload-js",
    cloakbrowser: "native-flag",
    notes:
      "CFT: defineProp on Navigator.prototype (quantized via deviceMemoryApiValue). CloakBrowser: --fingerprint-device-memory=",
  },
  {
    field: "seed",
    cft: "unsupported",
    cloakbrowser: "native-flag",
    notes:
      "CFT: not applicable — no canvas/audio noise. CloakBrowser: drives --fingerprint= seed for canvas/audio/WebGL readback noise",
  },
];

/**
 * Verify that every top-level field in FingerprintConfig is represented in the
 * launch contract. Returns the set of fields that are missing from the contract.
 */
export function findUncontractedFields(
  fpFields: string[],
): string[] {
  const contracted = new Set(LAUNCH_CONTRACT.map((c) => c.field.split(".")[0]));
  return fpFields.filter((f) => !contracted.has(f));
}

/**
 * Get the coverage level for a specific field on a specific engine.
 */
export function getCoverage(
  field: string,
  engine: BrowserEngine,
): CoverageLevel {
  const entry = LAUNCH_CONTRACT.find(
    (c) => c.field === field || c.field.startsWith(`${field}.`),
  );
  if (!entry) return "unsupported";
  return engine === "cloakbrowser" ? entry.cloakbrowser : entry.cft;
}

/**
 * Build the CloakBrowser CLI args and verify that every field expected to
 * have native coverage actually appears as a --fingerprint-* flag.
 */
export function verifyCloakBrowserNativeArgs(
  profileId: ProfileId,
  fp: FingerprintConfig,
): {
  args: string[];
  nativeFields: string[];
  missingNative: string[];
} {
  const args = buildCloakBrowserFingerprintArgs(profileId, fp);
  const nativeFields = LAUNCH_CONTRACT.filter(
    (c) => c.cloakbrowser === "native-flag",
  );

  // Map each native-flag field to the flag substring it should produce
  const fieldToFlag: Record<string, string> = {
    "userAgent": "--fingerprint-brand-version",
    "platform": "--fingerprint-platform",
    "clientHints.secChUa": "--fingerprint-brand-version",
    "clientHints.secChUaPlatform": "--fingerprint-platform",
    "clientHints.secChUaPlatformVersion": "--fingerprint-platform-version",
    "clientHints.secChUaFullVersionList": "--fingerprint-brand-version",
    "timezone": "--fingerprint-timezone",
    "screen.width": "--fingerprint-screen-width",
    "screen.height": "--fingerprint-screen-height",
    "webgl.vendor": "--fingerprint-gpu-vendor",
    "webgl.renderer": "--fingerprint-gpu-renderer",
    "hardwareConcurrency": "--fingerprint-hardware-concurrency",
    "deviceMemory": "--fingerprint-device-memory",
    "seed": "--fingerprint=",
    "device": "--fingerprint-platform",
  };

  const missing: string[] = [];
  for (const entry of nativeFields) {
    const expectedFlag = fieldToFlag[entry.field];
    if (!expectedFlag) {
      missing.push(`${entry.field} (no flag mapping)`);
      continue;
    }
    // For --fingerprint= (seed), check the prefix without = (it's --fingerprint=<number>)
    const checkStr = expectedFlag.endsWith("=")
      ? expectedFlag.slice(0, -1)
      : expectedFlag;
    if (!args.some((a) => a.startsWith(checkStr))) {
      // Some fields share a flag (e.g. userAgent and secChUa both use --fingerprint-brand-version).
      // If the flag exists at all, the field is covered.
      if (!args.some((a) => a.startsWith(checkStr))) {
        missing.push(entry.field);
      }
    }
  }

  return { args, nativeFields: nativeFields.map((f) => f.field), missingNative: missing };
}

/**
 * Verify that the preload script for CFT references every field that should
 * be applied via preload-js.
 */
export function verifyPreloadScriptFields(
  fp: FingerprintConfig,
): {
  script: string;
  preloadFields: string[];
  missingFromScript: string[];
} {
  const script = buildFingerprintPreloadScript(fp, { includeWebGl: true });
  const preloadFields = LAUNCH_CONTRACT.filter(
    (c) => c.cft === "preload-js",
  ).map((c) => c.field);

  // Map each preload-js field to the variable/token it should produce in the script
  const fieldToToken: Record<string, string> = {
    "platform": "PLATFORM",
    "availScreen": "AVAIL_W",
    "webgl.vendor": "GPU_VENDOR",
    "webgl.renderer": "GPU_RENDERER",
    "hardwareConcurrency": "HW_CONCURRENCY",
    "deviceMemory": "DEVICE_MEMORY",
  };

  const missing: string[] = [];
  for (const field of preloadFields) {
    const token = fieldToToken[field];
    if (!token) {
      missing.push(`${field} (no token mapping)`);
      continue;
    }
    if (!script.includes(token)) {
      missing.push(field);
    }
  }

  return { script, preloadFields, missingFromScript: missing };
}
