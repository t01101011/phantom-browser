import assert from "node:assert/strict";
import test from "node:test";
import { buildReport, normalizeEvidence, redact, renderSummary, SURFACES } from "./evidence.mjs";

const BASE = {
  engine: "cft",
  binary: { version: "151.0.7922.47", sha256: "a".repeat(64) },
  platform: { os: "linux", arch: "x64", headless: true },
};

test("stored profile fields and launch flags cannot become runtime evidence", () => {
  const report = buildReport({
    ...BASE,
    observations: {
      canvas: { status: "PASS", method: "stored-field", value: { seed: 123 } },
      timezone: { status: "NATIVE", method: "launch-flag", value: "Asia/Tokyo" },
    },
  });
  assert.equal(report.evidence.canvas.status, "UNKNOWN");
  assert.equal(report.evidence.timezone.status, "UNKNOWN");
  assert.equal(report.claims.nativeCoverage, "UNKNOWN");
});

test("only an actual observation with a value is accepted", () => {
  assert.deepEqual(
    normalizeEvidence("canvas", {
      status: "OBSERVED",
      method: "browser-runtime",
      value: { sha256: "abc" },
    }),
    {
      status: "OBSERVED",
      method: "browser-runtime",
      value: { sha256: "abc" },
    },
  );
  assert.equal(
    normalizeEvidence("canvas", { status: "OBSERVED", method: "browser-runtime" }).status,
    "UNKNOWN",
  );
});

test("every required surface is emitted and unavailable network evidence remains UNKNOWN", () => {
  const report = buildReport({ ...BASE, observations: {} });
  assert.deepEqual(Object.keys(report.evidence), SURFACES);
  for (const item of Object.values(report.evidence)) assert.equal(item.status, "UNKNOWN");
});

test("reports are engine-separated and never infer Cloak evidence from CFT", () => {
  const cft = buildReport({
    ...BASE,
    observations: { canvas: { status: "OBSERVED", method: "browser-runtime", value: 1 } },
  });
  const cloak = buildReport({ ...BASE, engine: "cloakbrowser", observations: {} });
  assert.equal(cft.engine.tag, "cft");
  assert.equal(cft.evidence.canvas.status, "OBSERVED");
  assert.equal(cloak.engine.tag, "cloakbrowser");
  assert.equal(cloak.evidence.canvas.status, "UNKNOWN");
});

test("recursive redaction removes common credential fields without deleting evidence", () => {
  const value = redact({
    proxyUrl: "http://user:pass@host",
    proxyRouting: { status: "UNKNOWN" },
    nested: { authorization: "Bearer x", result: 7 },
    cookie: "secret",
  });
  assert.deepEqual(value, {
    proxyUrl: "[REDACTED]",
    proxyRouting: { status: "UNKNOWN" },
    nested: { authorization: "[REDACTED]", result: 7 },
    cookie: "[REDACTED]",
  });
});

test("redaction covers credential variants and URLs embedded in values", () => {
  assert.deepEqual(
    redact({ api_key: "secret", accessToken: "secret", note: "go to http://user:pass@host/path" }),
    { api_key: "[REDACTED]", accessToken: "[REDACTED]", note: "go to [REDACTED_URL]" },
  );
});

test("untrusted evidence methods cannot inject summary control characters", () => {
  const report = buildReport({
    ...BASE,
    observations: { canvas: { status: "OBSERVED", method: "pcap\nINJECTED", value: 1 } },
  });
  assert.equal(report.evidence.canvas.status, "UNKNOWN");
  assert.equal(report.evidence.canvas.method, "not-observed");
  assert.doesNotMatch(renderSummary(report), /INJECTED/);
});

test("human summary includes immutable engine identity and UNKNOWN claim", () => {
  const summary = renderSummary(buildReport({ ...BASE, observations: {} }));
  assert.match(summary, /Engine: cft 151\.0\.7922\.47/);
  assert.match(summary, /Binary SHA-256: a{64}/);
  assert.match(summary, /Native coverage claim: UNKNOWN/);
});
