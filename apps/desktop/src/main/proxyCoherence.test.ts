import assert from "node:assert/strict";
import test from "node:test";
import { defaultFingerprint } from "../../../../packages/profile-manager/src/fingerprint.ts";
import { parseProxyGeoPayload, probeProxyGeo, type ProxyGeoResult } from "./proxyGeo.ts";
import { ProxyCoherenceError, resolveProxyCoherence } from "./proxyCoherence.ts";
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

    const cft = resolveProxyCoherence({ engine: "cft", fingerprint, geo: geo({ ip }) });
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
