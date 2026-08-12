import type { BrowserEngine } from "@multizen/settings-store";
import type { FingerprintConfig } from "@multizen/types";
import {
  findDeterministicLocaleIdByCountry,
  reconcileFingerprint,
} from "../../../../packages/profile-manager/src/fingerprint.ts";
import type { ProxyGeoResult } from "./proxyGeo";

export type GeoCoverage = "native-upstream" | "cdp-weaker" | "unavailable";

export interface ProxyCoherenceResult {
  fingerprint: FingerprintConfig;
  coordinates: { latitude: number; longitude: number } | null;
  webrtcIp: string | null;
  country: string | null;
  status: "coherent" | "degraded";
  issues: string[];
  geolocationCoverage: GeoCoverage;
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
    if (fingerprint.country.toLowerCase() !== proxyCountry) {
      const localeId = findDeterministicLocaleIdByCountry(proxyCountry);
      if (localeId) {
        fingerprint = reconcileFingerprint(fingerprint, {
          localeId,
          timezone: geo.timezone,
        });
      } else {
        issues.push(
          `Locale ${fingerprint.locale} does not match proxy country ${proxyCountry.toUpperCase()}, and no deterministic locale mapping exists`,
        );
      }
    }

    if (typeof geo.latitude !== "number" || typeof geo.longitude !== "number") {
      issues.push("Proxy geolocation response has no coordinates");
    }
  }

  const hasLocaleMismatch = issues.some((issue) => issue.startsWith("Locale "));
  if (
    (hasLocaleMismatch || (engine === "cloakbrowser" && issues.length > 0)) &&
    !params.acceptDegraded
  ) {
    throw new ProxyCoherenceError(issues);
  }

  const coordinates =
    geo && typeof geo.latitude === "number" && typeof geo.longitude === "number"
      ? { latitude: geo.latitude, longitude: geo.longitude }
      : null;

  return {
    fingerprint,
    coordinates,
    webrtcIp: geo?.ip || null,
    country: geo?.country.toLowerCase() || null,
    status: issues.length === 0 ? "coherent" : "degraded",
    issues,
    geolocationCoverage: coordinates
      ? engine === "cloakbrowser"
        ? "native-upstream"
        : "cdp-weaker"
      : "unavailable",
  };
}

function safeProbeError(error: unknown): string {
  const message = error instanceof Error ? error.message : "unknown error";
  if (/timed out/i.test(message)) return "timeout";
  if (/429|rate.?limit/i.test(message)) return "rate limited";
  return "unavailable";
}
