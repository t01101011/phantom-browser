import assert from "node:assert/strict";
import test from "node:test";
import { defaultFingerprint } from "../../../../packages/profile-manager/src/fingerprint.ts";
import { parseProxyGeoPayload, probeProxyGeo, type ProxyGeoResult } from "./proxyGeo.ts";
import { ProxyCoherenceError, resolveProxyCoherence } from "./proxyCoherence.ts";

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
