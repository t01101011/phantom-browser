import assert from "node:assert/strict";
import test from "node:test";
import { defaultFingerprint } from "../../../../packages/profile-manager/src/fingerprint.ts";
import { parseProxyGeoPayload, probeProxyGeo, type ProxyGeoResult } from "./proxyGeo.ts";
import {
  ProxyCoherenceError,
  canLaunchWithCoherence,
  precheckProxyCoherence,
  resolveProxyCoherence,
  summarizeCoherenceIssues,
} from "./proxyCoherence.ts";
import { applyCftGeolocationOverride } from "./cdpGeolocation.ts";

const PROXY = {
  type: "http" as const,
  host: "proxy.invalid",
  port: 8080,
  username: "secret-user",
  password: "secret-password",
};

function geo(overrides: Partial<ProxyGeoResult> = {}): ProxyGeoResult {
  return {
    country: "jp",
    countryName: "Japan",
    timezone: "Asia/Tokyo",
    city: "Tokyo",
    ip: "203.0.113.7",
    latitude: 35.6762,
    longitude: 139.6503,
    ...overrides,
  };
}

test("propagates a bounded proxy-probe timeout without exposing proxy secrets", async () => {
  await assert.rejects(
    probeProxyGeo(PROXY, {
      timeoutMs: 25,
      requestJson: async (_proxy, timeoutMs) => {
        assert.equal(timeoutMs, 25);
        throw new Error("proxy probe timed out");
      },
    }),
    (error: Error) => {
      assert.match(error.message, /timed out/);
      assert.doesNotMatch(error.message, /secret-user|secret-password|proxy\.invalid/);
      return true;
    },
  );
});

test("classifies provider rate limiting without logging credentials", () => {
  assert.throws(
    () =>
      parseProxyGeoPayload({
        ip: "",
        city: "",
        country_code: "",
        country_name: "",
        timezone: "",
        error: true,
        reason: "RateLimited",
      }),
    /RateLimited/,
  );
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: defaultFingerprint("rate-limit"),
    probeError: new Error("ipapi.co returned HTTP 429"),
  });
  assert.deepEqual(result.issues, ["Proxy geolocation probe failed (rate limited)"]);
});

test("rejects a proxy geo payload without a valid egress IP", () => {
  assert.throws(
    () =>
      parseProxyGeoPayload({
        ip: "not-an-ip",
        city: "Tokyo",
        country_code: "JP",
        country_name: "Japan",
        timezone: "Asia/Tokyo",
        latitude: 35.6762,
        longitude: 139.6503,
      }),
    /valid egress IP/,
  );
});

test("CloakBrowser fails closed when coordinates are missing", () => {
  assert.throws(
    () =>
      resolveProxyCoherence({
        engine: "cloakbrowser",
        fingerprint: defaultFingerprint("missing-coordinates"),
        geo: geo({ latitude: undefined, longitude: undefined }),
      }),
    ProxyCoherenceError,
  );
});

test("timezone-only results align timezone but remain degraded", () => {
  const fingerprint = { ...defaultFingerprint("timezone-only"), country: "jp", locale: "ja-JP" };
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint,
    geo: geo({ latitude: undefined, longitude: undefined }),
  });
  assert.equal(result.fingerprint.timezone, "Asia/Tokyo");
  assert.equal(result.status, "degraded");
  assert.equal(result.geolocationCoverage, "unavailable");
});

test("deterministic country mapping reconciles locale and languages automatically", () => {
  const result = resolveProxyCoherence({
    engine: "cloakbrowser",
    fingerprint: defaultFingerprint("deterministic-locale"),
    geo: geo(),
  });
  assert.equal(result.fingerprint.locale, "ja-JP");
  assert.deepEqual(result.fingerprint.languages, ["ja-JP", "ja", "en"]);
  assert.equal(result.status, "coherent");
});

test("same-country locale and language mismatch is reconciled as a full tuple", () => {
  const fingerprint = {
    ...defaultFingerprint("same-country-locale-mismatch"),
    country: "jp",
    locale: "en-US",
    languages: ["en-US", "en"],
    acceptLanguage: "en-US,en;q=0.9",
  };
  const result = resolveProxyCoherence({ engine: "cloakbrowser", fingerprint, geo: geo() });
  assert.equal(result.fingerprint.locale, "ja-JP");
  assert.deepEqual(result.fingerprint.languages, ["ja-JP", "ja", "en"]);
  assert.equal(result.fingerprint.acceptLanguage, "ja-JP,ja;q=0.9,en;q=0.8");
  assert.equal(result.status, "coherent");
});

for (const ip of ["", "not-an-ip", "999.2.3.4"]) {
  test(`invalid egress IP '${ip || "empty"}' is degraded and Cloak fails closed`, () => {
    const fingerprint = { ...defaultFingerprint(`invalid-ip-${ip}`), country: "jp" };
    const input = { engine: "cloakbrowser" as const, fingerprint, geo: geo({ ip }) };
    assert.throws(() => resolveProxyCoherence(input), ProxyCoherenceError);
    const accepted = resolveProxyCoherence({ ...input, acceptDegraded: true });
    assert.equal(accepted.status, "degraded");
    assert.equal(accepted.webrtcIp, null);
    assert.match(accepted.issues.join("; "), /valid egress IP/);

    // CFT with invalid IP is now fail-closed (WebRTC spoofing can't work without
    // a valid egress IP). It throws without acceptDegraded, returns degraded with it.
    assert.throws(
      () => resolveProxyCoherence({ engine: "cft", fingerprint, geo: geo({ ip }) }),
      ProxyCoherenceError,
    );
    const cft = resolveProxyCoherence({ engine: "cft", fingerprint, geo: geo({ ip }), acceptDegraded: true });
    assert.equal(cft.status, "degraded");
  });
}

test("ambiguous locale mismatch is visible instead of silently rewritten", () => {
  const input = {
    engine: "cft" as const,
    fingerprint: defaultFingerprint("ambiguous-locale"),
    geo: geo({ country: "be", countryName: "Belgium", timezone: "Europe/Brussels" }),
  };
  assert.throws(() => resolveProxyCoherence(input), ProxyCoherenceError);
  const result = resolveProxyCoherence({ ...input, acceptDegraded: true });
  assert.equal(result.status, "degraded");
  assert.match(result.issues[0] ?? "", /no deterministic locale mapping/);
});

test("explicit acceptance allows degraded CloakBrowser coherence", () => {
  assert.throws(
    () =>
      resolveProxyCoherence({
        engine: "cloakbrowser",
        fingerprint: defaultFingerprint("rejected-degraded"),
        probeError: new Error("proxy probe timed out"),
      }),
    ProxyCoherenceError,
  );
  const result = resolveProxyCoherence({
    engine: "cloakbrowser",
    fingerprint: defaultFingerprint("accepted-degraded"),
    probeError: new Error("proxy probe timed out"),
    acceptDegraded: true,
  });
  assert.equal(result.status, "degraded");
  assert.equal(result.geolocationCoverage, "unavailable");
});

test("reports native-upstream Cloak coverage and weaker CFT CDP coverage", () => {
  const fingerprint = { ...defaultFingerprint("engine-coverage"), country: "jp", locale: "ja-JP" };
  const cloak = resolveProxyCoherence({ engine: "cloakbrowser", fingerprint, geo: geo() });
  const cft = resolveProxyCoherence({ engine: "cft", fingerprint, geo: geo() });
  assert.equal(cloak.geolocationCoverage, "native-upstream");
  assert.equal(cft.geolocationCoverage, "cdp-weaker");
});

test("CFT geolocation override reports failure instead of claiming CDP coverage", async () => {
  const calls: string[] = [];
  const coherence = resolveProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("cdp-failure"), country: "jp" },
    geo: geo(),
  });
  const result = await applyCftGeolocationOverride(
    async (method: string) => {
      calls.push(method);
      throw new Error("CDP rejected geolocation override");
    },
    { latitude: 35.6762, longitude: 139.6503 },
    coherence,
  );
  assert.deepEqual(calls, ["Emulation.setGeolocationOverride"]);
  assert.equal(result, false);
  assert.equal(coherence.status, "degraded");
  assert.equal(coherence.geolocationCoverage, "unavailable");
  assert.match(coherence.issues.join("; "), /CDP geolocation fallback failed/);
});

// ── Item 8: recommendedAction + pre-launch visibility ─────────────────────

test("coherent result recommends launch", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("coherent-action"), country: "jp", locale: "ja-JP" },
    geo: geo(),
  });
  assert.equal(result.status, "coherent");
  assert.equal(result.recommendedAction, "launch");
});

test("CloakBrowser with any issue recommends fail-closed", () => {
  // Probe timeout
  assert.throws(
    () =>
      resolveProxyCoherence({
        engine: "cloakbrowser",
        fingerprint: defaultFingerprint("cloak-probe-fail"),
        probeError: new Error("proxy probe timed out"),
      }),
    ProxyCoherenceError,
  );
  const accepted = resolveProxyCoherence({
    engine: "cloakbrowser",
    fingerprint: defaultFingerprint("cloak-probe-accepted"),
    probeError: new Error("proxy probe timed out"),
    acceptDegraded: true,
  });
  assert.equal(accepted.recommendedAction, "fail-closed");
  assert.equal(accepted.status, "degraded");
});

test("CFT with locale mismatch recommends accept-degraded (not fail-closed)", () => {
  const fingerprint = {
    ...defaultFingerprint("cft-locale-mismatch-action"),
    country: "jp",
    locale: "en-US",
    languages: ["en-US", "en"],
    acceptLanguage: "en-US,en;q=0.9",
  };
  // Without acceptDegraded, throws
  assert.throws(
    () => resolveProxyCoherence({ engine: "cft", fingerprint, geo: geo({ country: "be", countryName: "Belgium", timezone: "Europe/Brussels" }) }),
    ProxyCoherenceError,
  );
  // With acceptDegraded, returns accept-degraded
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint,
    geo: geo({ country: "be", countryName: "Belgium", timezone: "Europe/Brussels" }),
    acceptDegraded: true,
  });
  assert.equal(result.recommendedAction, "accept-degraded");
});

test("CFT with invalid egress IP recommends fail-closed", () => {
  const fingerprint = { ...defaultFingerprint("cft-bad-ip-action"), country: "jp" };
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint,
    geo: geo({ ip: "not-an-ip" }),
    acceptDegraded: true,
  });
  assert.equal(result.recommendedAction, "fail-closed");
});

test("CFT with probe failure returns degraded (not fail-closed)", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: defaultFingerprint("cft-probe-fail-action"),
    probeError: new Error("proxy probe timed out"),
  });
  assert.equal(result.status, "degraded");
  assert.equal(result.recommendedAction, "accept-degraded");
});

// ── canLaunchWithCoherence ───────────────────────────────────────────────

test("canLaunchWithCoherence: launch action always allows", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("can-launch-ok"), country: "jp", locale: "ja-JP" },
    geo: geo(),
  });
  assert.equal(canLaunchWithCoherence(result, false), true);
  assert.equal(canLaunchWithCoherence(result, true), true);
});

test("canLaunchWithCoherence: accept-degraded respects the flag", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: defaultFingerprint("can-launch-degraded"),
    probeError: new Error("timed out"),
    acceptDegraded: true,
  });
  assert.equal(result.recommendedAction, "accept-degraded");
  assert.equal(canLaunchWithCoherence(result, false), false);
  assert.equal(canLaunchWithCoherence(result, true), true);
});

test("canLaunchWithCoherence: fail-closed respects the flag", () => {
  const result = resolveProxyCoherence({
    engine: "cloakbrowser",
    fingerprint: defaultFingerprint("can-launch-fail"),
    probeError: new Error("timed out"),
    acceptDegraded: true,
  });
  assert.equal(result.recommendedAction, "fail-closed");
  assert.equal(canLaunchWithCoherence(result, false), false);
  assert.equal(canLaunchWithCoherence(result, true), true);
});

// ── summarizeCoherenceIssues ─────────────────────────────────────────────

test("summarizeCoherenceIssues: OK for coherent result", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("summary-ok"), country: "jp", locale: "ja-JP" },
    geo: geo(),
  });
  assert.equal(summarizeCoherenceIssues(result), "Proxy coherence: OK");
});

test("summarizeCoherenceIssues: DEGRADED prefix for CFT issues", () => {
  const result = resolveProxyCoherence({
    engine: "cft",
    fingerprint: defaultFingerprint("summary-degraded"),
    probeError: new Error("timed out"),
    acceptDegraded: true,
  });
  const summary = summarizeCoherenceIssues(result);
  assert.match(summary, /^Proxy coherence: DEGRADED — /);
  assert.match(summary, /timeout/);
});

test("summarizeCoherenceIssues: FAIL prefix for CloakBrowser issues", () => {
  const result = resolveProxyCoherence({
    engine: "cloakbrowser",
    fingerprint: defaultFingerprint("summary-fail"),
    probeError: new Error("timed out"),
    acceptDegraded: true,
  });
  const summary = summarizeCoherenceIssues(result);
  assert.match(summary, /^Proxy coherence: FAIL — /);
});

// ── precheckProxyCoherence ────────────────────────────────────────────────

test("precheckProxyCoherence: returns coherent result on successful probe", async () => {
  const result = await precheckProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("precheck-ok"), country: "jp", locale: "ja-JP" },
    proxy: PROXY,
    probeGeo: async () => geo(),
  });
  assert.equal(result.status, "coherent");
  assert.equal(result.recommendedAction, "launch");
});

test("precheckProxyCoherence: returns degraded result on probe failure", async () => {
  const result = await precheckProxyCoherence({
    engine: "cft",
    fingerprint: defaultFingerprint("precheck-fail"),
    proxy: PROXY,
    probeGeo: async () => { throw new Error("proxy probe timed out"); },
    acceptDegraded: true,
  });
  assert.equal(result.status, "degraded");
  assert.equal(result.recommendedAction, "accept-degraded");
  assert.match(result.issues.join("; "), /timeout/);
});

test("precheckProxyCoherence: throws ProxyCoherenceError for CloakBrowser without acceptDegraded", async () => {
  await assert.rejects(
    precheckProxyCoherence({
      engine: "cloakbrowser",
      fingerprint: defaultFingerprint("precheck-cloak-fail"),
      proxy: PROXY,
      probeGeo: async () => { throw new Error("proxy probe timed out"); },
    }),
    ProxyCoherenceError,
  );
});

test("precheckProxyCoherence: uses injected probe function, not the real network", async () => {
  let called = false;
  const result = await precheckProxyCoherence({
    engine: "cft",
    fingerprint: { ...defaultFingerprint("precheck-injected"), country: "jp", locale: "ja-JP" },
    proxy: PROXY,
    probeGeo: async () => {
      called = true;
      return geo();
    },
  });
  assert.equal(called, true);
  assert.equal(result.status, "coherent");
});
