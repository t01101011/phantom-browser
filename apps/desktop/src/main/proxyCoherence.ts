import { isIP } from "node:net";
import type { BrowserEngine } from "@multizen/settings-store";
import type { FingerprintConfig, ProxyConfig } from "@multizen/types";
import {
  findDeterministicLocaleIdByCountry,
  reconcileFingerprint,
} from "../../../../packages/profile-manager/src/fingerprint.ts";
import { probeProxyGeo, type ProxyGeoResult } from "./proxyGeo.ts";

export type GeoCoverage = "native-upstream" | "cdp-weaker" | "unavailable";

export type CoherenceAction = "launch" | "accept-degraded" | "fail-closed";

export interface ProxyCoherenceResult {
  fingerprint: FingerprintConfig;
  coordinates: { latitude: number; longitude: number } | null;
  webrtcIp: string | null;
  country: string | null;
  status: "coherent" | "degraded";
  issues: string[];
  geolocationCoverage: GeoCoverage;
  /**
   * Recommended action based on coherence status + engine:
   * - "launch": coherence is good, proceed normally
   * - "accept-degraded": there are issues but the user can proceed after
   *   acknowledging them (CFT with locale mismatch, or probe failure)
   * - "fail-closed": CloakBrowser (stealth) with unresolved coherence —
   *   launching would expose the persona, so refuse unless the user
   *   explicitly accepts degraded mode
   */
  recommendedAction: CoherenceAction;
}

export class ProxyCoherenceError extends Error {
  readonly issues: string[];

  constructor(issues: string[]) {
    super(`Proxy coherence check requires explicit degraded-mode acceptance: ${issues.join("; ")}`);
    this.name = "ProxyCoherenceError";
    this.issues = issues;
  }
}

export function resolveProxyCoherence(params: {
  engine: BrowserEngine;
  fingerprint: FingerprintConfig;
  geo?: ProxyGeoResult;
  probeError?: unknown;
  acceptDegraded?: boolean;
}): ProxyCoherenceResult {
  const { engine, geo } = params;
  let fingerprint = params.fingerprint;
  const issues: string[] = [];

  if (!geo) {
    issues.push(`Proxy geolocation probe failed (${safeProbeError(params.probeError)})`);
  } else {
    if (geo.timezone !== fingerprint.timezone) {
      fingerprint = { ...fingerprint, timezone: geo.timezone };
    }

    const proxyCountry = geo.country.toLowerCase();
    const localeId = findDeterministicLocaleIdByCountry(proxyCountry);
    if (localeId) {
      const reconciled = reconcileFingerprint(fingerprint, {
        localeId,
        timezone: geo.timezone,
      });
      if (!hasSameLocaleTuple(fingerprint, reconciled)) fingerprint = reconciled;
    } else if (fingerprint.country.toLowerCase() !== proxyCountry) {
      issues.push(
        `Locale ${fingerprint.locale} does not match proxy country ${proxyCountry.toUpperCase()}, and no deterministic locale mapping exists`,
      );
    }

    if (typeof geo.latitude !== "number" || typeof geo.longitude !== "number") {
      issues.push("Proxy geolocation response has no coordinates");
    }
    if (isIP(geo.ip) === 0) {
      issues.push("Proxy geolocation response has no valid egress IP");
    }
  }

  // ── Recommended action ───────────────────────────────────────────────
  // CloakBrowser is a stealth engine — launching with unresolved coherence
  // defeats its purpose. CFT is weaker anyway so degraded mode is more
  // acceptable, but the user should still see the issues.
  const hasLocaleMismatch = issues.some((issue) => issue.startsWith("Locale "));
  const hasProbeFailure = issues.some((issue) =>
    issue.startsWith("Proxy geolocation probe failed"),
  );
  const hasMissingCoords = issues.some((issue) =>
    issue.startsWith("Proxy geolocation response has no coordinates"),
  );
  const hasInvalidIp = issues.some((issue) =>
    issue.startsWith("Proxy geolocation response has no valid egress IP"),
  );

  let recommendedAction: CoherenceAction;
  if (issues.length === 0) {
    recommendedAction = "launch";
  } else if (engine === "cloakbrowser") {
    // CloakBrowser (stealth): fail-closed for ANY issue that undermines the
    // persona's geographic identity — locale mismatch, missing coords, or
    // invalid egress IP. A probe timeout alone (rate limit, network) is
    // softer — the user can retry, but we still flag it as fail-closed
    // because without geo data CloakBrowser's native geolocation flag
    // can't be set and the persona location will be wrong.
    recommendedAction = "fail-closed";
  } else {
    // CFT: degraded mode is acceptable if the user acknowledges the issues.
    // Locale mismatch and missing coords lower the stealth quality but
    // don't create an active leak (CFT's CDP overrides are weaker but
    // functional). An invalid egress IP is more serious — without it
    // WebRTC spoofing can't work.
    if (hasInvalidIp) {
      recommendedAction = "fail-closed";
    } else {
      recommendedAction = "accept-degraded";
    }
  }

  // ── Fail-closed enforcement ───────────────────────────────────────────
  // Only throw when the recommended action is "fail-closed" and the user
  // hasn't accepted degraded mode. For "accept-degraded" on CFT, we also
  // throw for locale mismatches (preserving the old behavior the tests
  // depend on), but NOT for probe failures alone — those return a degraded
  // result so the GUI can surface the issue without blocking.
  if (recommendedAction === "fail-closed" && !params.acceptDegraded) {
    throw new ProxyCoherenceError(issues);
  }

  // CFT locale mismatch: preserve old behavior (throw without acceptDegraded)
  if (recommendedAction === "accept-degraded" && hasLocaleMismatch && !params.acceptDegraded) {
    throw new ProxyCoherenceError(issues);
  }

  const coordinates =
    geo && typeof geo.latitude === "number" && typeof geo.longitude === "number"
      ? { latitude: geo.latitude, longitude: geo.longitude }
      : null;

  return {
    fingerprint,
    coordinates,
    webrtcIp: geo && isIP(geo.ip) !== 0 ? geo.ip : null,
    country: geo?.country.toLowerCase() || null,
    status: issues.length === 0 ? "coherent" : "degraded",
    issues,
    // The pinned CloakBrowser build does not expose a verified native
    // geolocation flag. Both engines use the target-scoped CDP fallback.
    geolocationCoverage: coordinates ? "cdp-weaker" : "unavailable",
    recommendedAction,
  };
}

/**
 * Pre-launch coherence check — probe the proxy geo and resolve coherence
 * WITHOUT spawning a browser. Returns a structured result so the GUI can
 * surface issues and ask the user to accept degraded mode before launch.
 *
 * This is the "visibility before launch" layer: instead of discovering
 * coherence issues mid-launch (after the browser is already spawning),
 * the GUI calls this when the user clicks Launch, shows the issues if
 * any, and only proceeds (with `acceptDegraded: true`) after the user
 * acknowledges them.
 */
export async function precheckProxyCoherence(params: {
  engine: BrowserEngine;
  fingerprint: FingerprintConfig;
  proxy: ProxyConfig;
  timeoutMs?: number;
  acceptDegraded?: boolean;
  probeGeo?: (proxy: ProxyConfig, opts?: { timeoutMs?: number }) => Promise<ProxyGeoResult>;
}): Promise<ProxyCoherenceResult> {
  const {
    engine,
    fingerprint,
    proxy,
    timeoutMs = 4000,
    acceptDegraded = false,
    probeGeo = probeProxyGeo,
  } = params;

  try {
    const geo = await probeGeo(proxy, { timeoutMs });
    return resolveProxyCoherence({ engine, fingerprint, geo, acceptDegraded });
  } catch (error) {
    if (error instanceof ProxyCoherenceError) throw error;
    return resolveProxyCoherence({
      engine,
      fingerprint,
      probeError: error,
      acceptDegraded,
    });
  }
}

/**
 * Determines whether a coherence result should block the launch entirely
 * (no amount of "accept degraded" can make it safe) or merely warn.
 *
 * Returns true if the launch can proceed (possibly with degraded mode),
 * false if it must be blocked.
 */
export function canLaunchWithCoherence(
  result: ProxyCoherenceResult,
  acceptDegraded: boolean,
): boolean {
  if (result.recommendedAction === "launch") return true;
  if (result.recommendedAction === "accept-degraded") return acceptDegraded;
  // fail-closed: only allow with explicit acceptance
  return acceptDegraded;
}

/**
 * Human-readable summary of coherence issues for the launch UI.
 * Returns a single string suitable for a dialog or banner.
 */
export function summarizeCoherenceIssues(result: ProxyCoherenceResult): string {
  if (result.issues.length === 0) return "Proxy coherence: OK";
  const prefix =
    result.recommendedAction === "fail-closed"
      ? "Proxy coherence: FAIL — "
      : "Proxy coherence: DEGRADED — ";
  return prefix + result.issues.join("; ");
}

function hasSameLocaleTuple(left: FingerprintConfig, right: FingerprintConfig): boolean {
  return (
    left.country.toLowerCase() === right.country.toLowerCase() &&
    left.locale === right.locale &&
    left.acceptLanguage === right.acceptLanguage &&
    left.languages.length === right.languages.length &&
    left.languages.every((language, index) => language === right.languages[index])
  );
}

function safeProbeError(error: unknown): string {
  const message = error instanceof Error ? error.message : "unknown error";
  const providers = ["ipwho.is", "ipapi.co", "ip-api.com", "ipapi.is"];
  const providerResults = providers
    .map((provider) => {
      const match = message.match(new RegExp(`${provider.replaceAll(".", "\\.")}: ([^;]+)`, "i"));
      if (!match) return null;
      return `${provider}: ${safeProbeCategory(match[1] ?? "")}`;
    })
    .filter((result): result is string => result !== null);
  if (providerResults.length > 0) return providerResults.join("; ");
  return safeProbeCategory(message);
}

function safeProbeCategory(message: string): string {
  if (/timed out|timeout/i.test(message)) return "timeout";
  if (/429|rate.?limit/i.test(message)) return "rate limited";
  const status = message.match(/HTTP (4\d\d|5\d\d)/i)?.[1];
  if (status) return `HTTP ${status}`;
  return "unavailable";
}
