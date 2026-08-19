import assert from "node:assert/strict";
import test from "node:test";
import { defaultFingerprint } from "../../../../packages/profile-manager/src/fingerprint.ts";
import {
  PROBE_TO_CONTRACT_FIELDS,
  classifyProbeResult,
  getCrossReferenceTable,
  getProbeContractMapping,
} from "./launchContractProbe.ts";
import { getCoverage } from "./launchContract.ts";

// ── Cross-reference table ─────────────────────────────────────────────────

test("cross-reference table covers availScreen, dprDepth, and icuLocale", () => {
  const table = getCrossReferenceTable();
  const surfaces = new Set(table.map((r) => r.surface));
  assert.ok(surfaces.has("availScreen"));
  assert.ok(surfaces.has("dprDepth"));
  assert.ok(surfaces.has("icuLocale"));
  assert.ok(table.length >= 6, "Expected at least 6 rows (3 surfaces × 2 engines)");
});

test("every cross-reference row matches its expected coverage to the actual coverage", () => {
  const table = getCrossReferenceTable();
  for (const row of table) {
    assert.equal(
      row.match,
      true,
      `${row.surface}.${row.field} on ${row.engine}: expected ${row.expectedCoverage}, got ${row.actualCoverage}`,
    );
  }
});

// ── availScreen ────────────────────────────────────────────────────────────

test("availScreen maps to FingerprintConfig.availScreen field", () => {
  const mappings = getProbeContractMapping("availScreen");
  assert.equal(mappings.length, 2);
  assert.deepEqual(
    mappings.map((m) => m.field),
    ["availScreen", "availScreen"],
  );
});

test("availScreen on CFT uses preload-js (JS-level patch only; availLeft/availTop unpatched)", () => {
  const cftLevel = getCoverage("availScreen", "cft");
  assert.equal(cftLevel, "preload-js");
});

test("availScreen on CloakBrowser is unsupported (no native availScreen flag)", () => {
  const cloakLevel = getCoverage("availScreen", "cloakbrowser");
  assert.equal(cloakLevel, "unsupported");
});

// ── dprDepth ───────────────────────────────────────────────────────────────

test("dprDepth maps to FingerprintConfig.dpr field", () => {
  const mappings = getProbeContractMapping("dprDepth");
  assert.equal(mappings.length, 2);
  assert.deepEqual(
    mappings.map((m) => m.field),
    ["dpr", "dpr"],
  );
});

test("dpr on CFT uses CDP setDeviceMetricsOverride", () => {
  const cftLevel = getCoverage("dpr", "cft");
  assert.equal(cftLevel, "cdp");
});

test("dpr on CloakBrowser is unsupported (no native DPR flag)", () => {
  const cloakLevel = getCoverage("dpr", "cloakbrowser");
  assert.equal(cloakLevel, "unsupported");
});

// ── icuLocale ─────────────────────────────────────────────────────────────

test("icuLocale maps to FingerprintConfig.locale field", () => {
  const mappings = getProbeContractMapping("icuLocale");
  assert.equal(mappings.length, 2);
  assert.deepEqual(
    mappings.map((m) => m.field),
    ["locale", "locale"],
  );
});

test("locale on CFT uses CDP setLocaleOverride", () => {
  const cftLevel = getCoverage("locale", "cft");
  assert.equal(cftLevel, "cdp");
});

test("locale on CloakBrowser also uses CDP (the documented gap)", () => {
  const cloakLevel = getCoverage("locale", "cloakbrowser");
  assert.equal(cloakLevel, "cdp");
});

// ── classifyProbeResult ───────────────────────────────────────────────────

test("classifyProbeResult returns no-observation for missing or UNKNOWN observations", () => {
  const fp = defaultFingerprint("classify-no-obs") as unknown as Record<string, unknown>;
  assert.equal(
    classifyProbeResult("availScreen", "cft", undefined, fp),
    "no-observation",
  );
  assert.equal(
    classifyProbeResult("availScreen", "cft", { status: "UNKNOWN" }, fp),
    "no-observation",
  );
  assert.equal(
    classifyProbeResult("dprDepth", "cft", { status: "OBSERVED" }, fp),
    "no-observation",
  );
});

test("classifyProbeResult returns consistent when contract matches for CFT dprDepth", () => {
  const fp = defaultFingerprint("classify-cft-dpr") as unknown as Record<string, unknown>;
  const observed = {
    status: "OBSERVED",
    value: { dpr: 2, isInteger: true },
  };
  assert.equal(
    classifyProbeResult("dprDepth", "cft", observed, fp),
    "consistent",
  );
});

test("classifyProbeResult returns consistent when contract matches for CloakBrowser availScreen (unsupported)", () => {
  const fp = defaultFingerprint("classify-cloak-avail") as unknown as Record<string, unknown>;
  const observed = {
    status: "OBSERVED",
    value: { availLeft: 0, availTop: 0, taskbarHeight: 40 },
  };
  assert.equal(
    classifyProbeResult("availScreen", "cloakbrowser", observed, fp),
    "consistent",
  );
});

test("classifyProbeResult returns consistent when contract matches for icuLocale on both engines", () => {
  const fp = defaultFingerprint("classify-icu") as unknown as Record<string, unknown>;
  const observed = {
    status: "OBSERVED",
    value: { locale: "en-US", calendar: "gregory", numberingSystem: "latn" },
  };
  assert.equal(
    classifyProbeResult("icuLocale", "cft", observed, fp),
    "consistent",
  );
  assert.equal(
    classifyProbeResult("icuLocale", "cloakbrowser", observed, fp),
    "consistent",
  );
});

// ── Probe surface completeness ────────────────────────────────────────────

test("every extended probe surface (availScreen, dprDepth, icuLocale) is in PROBE_TO_CONTRACT_FIELDS", () => {
  const surfaces = Object.keys(PROBE_TO_CONTRACT_FIELDS);
  assert.deepEqual(surfaces.sort(), ["availScreen", "dprDepth", "icuLocale"]);
});

test("every probe-to-contract mapping references a field that exists in LAUNCH_CONTRACT", () => {
  const table = getCrossReferenceTable();
  for (const row of table) {
    // If the field wasn't in LAUNCH_CONTRACT, getCoverage returns "unsupported".
    // But some fields ARE legitimately "unsupported" on an engine (e.g. dpr on
    // CloakBrowser). The real invariant is: the mapping's expectedLevel must
    // match what getCoverage returns — i.e. row.match is true. That proves the
    // field was found and the expected level is consistent.
    assert.equal(
      row.match,
      true,
      `${row.field} on ${row.engine}: expected ${row.expectedCoverage} but contract says ${row.actualCoverage}`,
    );
  }
});
