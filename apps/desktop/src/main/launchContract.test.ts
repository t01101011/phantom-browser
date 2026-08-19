import assert from "node:assert/strict";
import test from "node:test";
import { defaultFingerprint } from "../../../../packages/profile-manager/src/fingerprint.ts";
import type { FingerprintConfig } from "@multizen/types";
import {
  LAUNCH_CONTRACT,
  buildCloakBrowserFingerprintArgs,
  buildFingerprintPreloadScript,
  buildUserAgentMetadata,
  deviceMemoryApiValue,
  findUncontractedFields,
  fingerprintSeed,
  getCoverage,
  parseBrandList,
  primaryBrandVersion,
  reconcileVersionInFingerprint,
  verifyCloakBrowserNativeArgs,
  verifyPreloadScriptFields,
  type CoverageLevel,
} from "./launchContract.ts";

const TEST_FP: FingerprintConfig = defaultFingerprint("launch-contract-test");

// ── Contract completeness ───────────────────────────────────────────────────

test("every top-level FingerprintConfig field appears in the launch contract", () => {
  const fpFields = [
    "device",
    "userAgent",
    "platform",
    "clientHints",
    "locale",
    "languages",
    "acceptLanguage",
    "timezone",
    "country",
    "screen",
    "availScreen",
    "dpr",
    "webgl",
    "hardwareConcurrency",
    "deviceMemory",
    "seed",
  ];
  const missing = findUncontractedFields(fpFields);
  assert.deepEqual(missing, [], `Fields missing from contract: ${missing.join(", ")}`);
});

test("every contract entry has a valid coverage level for both engines", () => {
  const valid: CoverageLevel[] = [
    "native-flag",
    "cli-flag",
    "cdp",
    "preload-js",
    "unsupported",
  ];
  for (const entry of LAUNCH_CONTRACT) {
    assert.ok(
      valid.includes(entry.cft),
      `${entry.field}: cft="${entry.cft}" is not a valid CoverageLevel`,
    );
    assert.ok(
      valid.includes(entry.cloakbrowser),
      `${entry.field}: cloakbrowser="${entry.cloakbrowser}" is not a valid CoverageLevel`,
    );
  }
});

test("no field is silently unsupported on both engines without a notes explanation", () => {
  for (const entry of LAUNCH_CONTRACT) {
    if (entry.cft === "unsupported" && entry.cloakbrowser === "unsupported") {
      assert.ok(
        entry.notes,
        `${entry.field} is unsupported on both engines but has no notes explaining why`,
      );
    }
  }
});

// ── CloakBrowser native args ───────────────────────────────────────────────

test("CloakBrowser CLI args include a --fingerprint flag for every native-flag field", () => {
  const { args, missingNative } = verifyCloakBrowserNativeArgs(
    "test-profile",
    TEST_FP,
  );
  assert.deepEqual(missingNative, [], `Missing native flags: ${missingNative.join(", ")}`);
  assert.ok(args.length >= 8, `Expected ≥8 CloakBrowser args, got ${args.length}`);
});

test("CloakBrowser arg values match the fingerprint config", () => {
  const args = buildCloakBrowserFingerprintArgs("test-profile", TEST_FP);
  const argStr = args.join(" ");

  // Timezone
  assert.ok(
    argStr.includes(`--fingerprint-timezone=${TEST_FP.timezone}`),
    "timezone not found in args",
  );
  // Screen
  assert.ok(
    argStr.includes(`--fingerprint-screen-width=${TEST_FP.screen.width}`),
    "screen width not found",
  );
  assert.ok(
    argStr.includes(`--fingerprint-screen-height=${TEST_FP.screen.height}`),
    "screen height not found",
  );
  // Hardware concurrency
  assert.ok(
    argStr.includes(`--fingerprint-hardware-concurrency=${TEST_FP.hardwareConcurrency}`),
    "hardwareConcurrency not found",
  );
  // Device memory (quantized)
  assert.ok(
    argStr.includes(`--fingerprint-device-memory=${deviceMemoryApiValue(TEST_FP.deviceMemory)}`),
    "deviceMemory not found",
  );
  // WebGL
  assert.ok(
    argStr.includes(`--fingerprint-gpu-vendor=${TEST_FP.webgl.vendor}`),
    "webgl vendor not found",
  );
  assert.ok(
    argStr.includes(`--fingerprint-gpu-renderer=${TEST_FP.webgl.renderer}`),
    "webgl renderer not found",
  );
});

test("CloakBrowser seed is deterministic and derived from profile id or explicit seed", () => {
  const seed1 = fingerprintSeed("profile-a", TEST_FP);
  const seed2 = fingerprintSeed("profile-a", TEST_FP);
  const seed3 = fingerprintSeed("profile-b", TEST_FP);

  assert.equal(seed1, seed2, "same profile+fp should produce same seed");
  assert.notEqual(seed1, seed3, "different profiles should produce different seeds");

  // With explicit seed on fp
  const fpWithSeed = { ...TEST_FP, seed: "explicit-seed-123" };
  const explicitSeed = fingerprintSeed("profile-a", fpWithSeed);
  const explicitSeed2 = fingerprintSeed("profile-b", fpWithSeed);
  assert.equal(
    explicitSeed,
    explicitSeed2,
    "explicit fp.seed should produce same CloakBrowser seed regardless of profile id",
  );
});

// ── CFT preload script ─────────────────────────────────────────────────────

test("CFT preload script covers every preload-js field", () => {
  const { script, missingFromScript } = verifyPreloadScriptFields(TEST_FP);
  assert.deepEqual(missingFromScript, [], `Missing from preload: ${missingFromScript.join(", ")}`);
  assert.ok(script.length > 100, "Preload script is suspiciously short");
});

test("CFT preload script injects the correct values from the fingerprint", () => {
  const script = buildFingerprintPreloadScript(TEST_FP, { includeWebGl: true });

  // Platform
  assert.ok(
    script.includes(JSON.stringify(TEST_FP.platform)),
    "platform value not found in preload script",
  );
  // Hardware concurrency
  assert.ok(
    script.includes(`HW_CONCURRENCY = ${TEST_FP.hardwareConcurrency}`),
    "hardwareConcurrency not found",
  );
  // Device memory (quantized)
  assert.ok(
    script.includes(`DEVICE_MEMORY = ${deviceMemoryApiValue(TEST_FP.deviceMemory)}`),
    "deviceMemory not found",
  );
  // WebGL
  assert.ok(
    script.includes(JSON.stringify(TEST_FP.webgl.vendor)),
    "webgl vendor not found",
  );
  assert.ok(
    script.includes(JSON.stringify(TEST_FP.webgl.renderer)),
    "webgl renderer not found",
  );
  // Screen
  assert.ok(
    script.includes(`SCREEN_W = ${TEST_FP.screen.width}`),
    "screen width not found",
  );
  assert.ok(
    script.includes(`SCREEN_H = ${TEST_FP.screen.height}`),
    "screen height not found",
  );
  // DPR
  assert.ok(
    script.includes(`DPR = ${TEST_FP.dpr}`),
    "dpr not found",
  );
  // AvailScreen (falls back to screen if unset)
  const expectedAvailW = TEST_FP.availScreen?.width ?? TEST_FP.screen.width;
  assert.ok(
    script.includes(`AVAIL_W = ${expectedAvailW}`),
    "availScreen width not found",
  );
});

test("preload script with includeWebGl=false omits WebGL patches", () => {
  const script = buildFingerprintPreloadScript(TEST_FP, { includeWebGl: false });
  assert.ok(script.includes("INCLUDE_WEBGL = false"));
  // The WebGL patch functions are still defined but the conditionals skip them
  assert.ok(script.includes("patchGetParameter"), "patchGetParameter should still be defined");
});

// ── CDP UA metadata ────────────────────────────────────────────────────────

test("buildUserAgentMetadata converts ClientHints to CDP userAgentMetadata", () => {
  const meta = buildUserAgentMetadata(TEST_FP);
  const ch = TEST_FP.clientHints;

  assert.equal(meta.platform, ch.secChUaPlatform);
  assert.equal(meta.platformVersion, ch.secChUaPlatformVersion);
  assert.equal(meta.architecture, ch.secChUaArch);
  assert.equal(meta.bitness, ch.secChUaBitness);
  assert.equal(meta.model, ch.secChUaModel);
  assert.equal(meta.mobile, ch.secChUaMobile === "?1");
  assert.equal(meta.wow64, false);
  assert.ok(meta.brands.length >= 1, "brands array should not be empty");
  assert.ok(meta.fullVersionList.length >= 1, "fullVersionList should not be empty");
});

test("parseBrandList extracts brand/version pairs from Sec-CH-UA header format", () => {
  const header = `"Chromium";v="148", "Google Chrome";v="148", "Not?A_Brand";v="99"`;
  const brands = parseBrandList(header);
  assert.equal(brands.length, 3);
  assert.deepEqual(brands[0], { brand: "Chromium", version: "148" });
  assert.deepEqual(brands[2], { brand: "Not?A_Brand", version: "99" });
});

test("primaryBrandVersion extracts the first non-Chromium, non-GREASE version", () => {
  const ch = {
    secChUa: `"Chromium";v="148", "Google Chrome";v="148", "Not?A_Brand";v="99"`,
    secChUaFullVersionList: `"Chromium";v="148.0.7202.93", "Google Chrome";v="148.0.7202.93", "Not.A/Brand";v="99.0.0.0"`,
  } as unknown as import("@multizen/types").ClientHints;
  assert.equal(primaryBrandVersion(ch), "148.0.7202.93");
});

test("primaryBrandVersion returns null for missing full-version-list", () => {
  assert.equal(primaryBrandVersion(undefined), null);
  // Cast through unknown to avoid excess-property checking on a partial object
  const partial = {
    secChUa: "",
    secChUaFullVersionList: "",
  } as unknown as import("@multizen/types").ClientHints;
  assert.equal(primaryBrandVersion(partial), null);
});

// ── deviceMemoryApiValue ───────────────────────────────────────────────────

test("deviceMemoryApiValue quantizes physical RAM to powers of two, capped at 8", () => {
  assert.equal(deviceMemoryApiValue(8), 8);
  assert.equal(deviceMemoryApiValue(16), 8, "16 GB should be capped to 8");
  assert.equal(deviceMemoryApiValue(32), 8, "32 GB should be capped to 8");
  assert.equal(deviceMemoryApiValue(4), 4);
  assert.equal(deviceMemoryApiValue(2), 2);
  assert.equal(deviceMemoryApiValue(6), 8, "6 → round(log2(6))=round(2.58)=3 → 2^3=8");
  assert.equal(deviceMemoryApiValue(12), 8, "12 → round(log2(12))=round(3.58)=4 → 2^4=16 → capped 8");
  assert.equal(deviceMemoryApiValue(0), 8, "0 → default 8");
  assert.equal(deviceMemoryApiValue(-1), 8, "negative → default 8");
});

// ── Version reconciliation ─────────────────────────────────────────────────

test("reconcileVersionInFingerprint rewrites UA and Client Hints versions", () => {
  const result = reconcileVersionInFingerprint(TEST_FP, {
    major: 151,
    full: "151.0.7922.47",
  });

  assert.ok(
    result.userAgent.includes("Chrome/151.0.7922.47"),
    "UA should contain the new version",
  );
  assert.ok(
    !result.userAgent.includes("Chrome/148."),
    "UA should not contain old version",
  );
  assert.ok(
    result.clientHints.secChUa.includes(`v="151"`),
    "secChUa should contain new major version",
  );
  assert.ok(
    result.clientHints.secChUaFullVersionList.includes(`v="151.0.7922.47"`),
    "secChUaFullVersionList should contain new full version",
  );
});

test("reconcileVersionInFingerprint preserves non-version fields", () => {
  const result = reconcileVersionInFingerprint(TEST_FP, {
    major: 151,
    full: "151.0.7922.47",
  });
  assert.equal(result.device, TEST_FP.device);
  assert.equal(result.locale, TEST_FP.locale);
  assert.equal(result.timezone, TEST_FP.timezone);
  assert.deepEqual(result.screen, TEST_FP.screen);
  assert.equal(result.hardwareConcurrency, TEST_FP.hardwareConcurrency);
});

// ── getCoverage ────────────────────────────────────────────────────────────

test("getCoverage returns the right level for known fields", () => {
  assert.equal(getCoverage("timezone", "cft"), "cdp");
  assert.equal(getCoverage("timezone", "cloakbrowser"), "native-flag");
  assert.equal(getCoverage("webgl.vendor", "cft"), "preload-js");
  assert.equal(getCoverage("webgl.vendor", "cloakbrowser"), "native-flag");
  assert.equal(getCoverage("country", "cft"), "unsupported");
  assert.equal(getCoverage("country", "cloakbrowser"), "unsupported");
});

test("getCoverage returns unsupported for unknown fields", () => {
  assert.equal(getCoverage("nonexistent", "cft"), "unsupported");
  assert.equal(getCoverage("nonexistent", "cloakbrowser"), "unsupported");
});

// ── CloakBrowser locale is the documented gap ──────────────────────────────

test("CloakBrowser locale is the only field applied via CDP instead of native", () => {
  const localeEntry = LAUNCH_CONTRACT.find((c) => c.field === "locale")!;
  assert.equal(localeEntry.cloakbrowser, "cdp");
  assert.ok(
    localeEntry.notes?.includes("no native locale switch"),
    "notes should explain CloakBrowser has no native locale flag",
  );
});

// ── Contract encoding invariants ───────────────────────────────────────────

test("no field is applied via preload-js on CloakBrowser", () => {
  // CloakBrowser handles all fingerprinting in C++; layering JS patches on top
  // would create double-spoof anomalies.
  for (const entry of LAUNCH_CONTRACT) {
    assert.notEqual(
      entry.cloakbrowser,
      "preload-js",
      `${entry.field} should not use preload-js on CloakBrowser`,
    );
  }
});

test("fields with cdt coverage also have a notes entry", () => {
  for (const entry of LAUNCH_CONTRACT) {
    if (entry.cft === "cdp" || entry.cloakbrowser === "cdp") {
      assert.ok(
        entry.notes,
        `${entry.field} uses CDP but has no notes explaining the method`,
      );
    }
  }
});
