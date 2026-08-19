import { createHash } from "node:crypto";

export const HARNESS_SCHEMA_VERSION = 1;
export const SURFACES = [
  "canvas",
  "audioContext",
  "webgl",
  "fonts",
  "domRect",
  "uaClientHints",
  "screen",
  "cpuRam",
  "timezone",
  "localeLanguages",
  "geolocation",
  "webrtc",
  "proxyRouting",
  "dns",
  "tlsJa3Ja4",
  "http2Settings",
  "http3Quic",
  // ── Extended surfaces (Item 7) ───────────────────────────────────────
  // Dedicated probes for fingerprint surfaces that the coarse screen/locale
  // probes only partially cover. These connect runtime observations back to
  // the launch-contract coverage declarations.
  "availScreen",  // screen.availLeft/availTop + taskbar deduction (unpatched on CFT)
  "dprDepth",     // devicePixelRatio quantization + matchMedia resolution queries
  "icuLocale",    // deep ICU locale: calendar, numberingSystem, hourCycle, collation
];

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function observed(value, method = "browser-runtime") {
  return { status: "OBSERVED", method, value };
}

export function unknown(reason, method = "not-observed") {
  return { status: "UNKNOWN", method, reason };
}

export function normalizeEvidence(surface, candidate) {
  if (!SURFACES.includes(surface)) throw new Error(`Unknown coverage surface: ${surface}`);
  if (
    !candidate ||
    candidate.status !== "OBSERVED" ||
    candidate.value === undefined ||
    typeof candidate.method !== "string" ||
    !/^[a-z0-9-]{1,40}$/.test(candidate.method)
  ) {
    return unknown(candidate?.reason ?? "No runtime observation was captured");
  }
  return observed(candidate.value, candidate.method);
}

export function buildReport({
  engine,
  binary,
  platform,
  observations,
  network = {},
  runId = null,
}) {
  if (engine !== "cft" && engine !== "cloakbrowser") {
    throw new Error(`Unsupported engine tag: ${engine}`);
  }
  const evidence = {};
  for (const surface of SURFACES) {
    evidence[surface] = normalizeEvidence(surface, observations[surface] ?? network[surface]);
  }
  return {
    schemaVersion: HARNESS_SCHEMA_VERSION,
    harness: "phantom-native-coverage",
    generatedAt: new Date().toISOString(),
    runId,
    engine: {
      tag: engine,
      version: binary.version ?? null,
      releaseTag: binary.releaseTag ?? null,
      sha256: binary.sha256,
    },
    platform: {
      os: platform.os,
      arch: platform.arch,
      headless: platform.headless,
    },
    evidence,
    claims: {
      nativeCoverage: "UNKNOWN",
      note: "Runtime observations prove page-visible behavior only; they do not prove a native Chromium patch or anti-bot bypass.",
    },
  };
}

export function redact(value) {
  const secretKey =
    /^(authorization|cookie|password|passwd|proxy[-_]?url|proxy[-_]?(password|username)|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|username)$/i;
  if (Array.isArray(value)) return value.map(redact);
  if (typeof value === "string") {
    return value.replace(/\bhttps?:\/\/[^\s/:]+:[^\s@]+@[^\s]+/gi, "[REDACTED_URL]");
  }
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      secretKey.test(key) ? "[REDACTED]" : redact(item),
    ]),
  );
}

export function renderSummary(report) {
  const lines = [
    `Phantom native coverage harness v${report.schemaVersion}`,
    `Engine: ${report.engine.tag} ${report.engine.version ?? "unknown"}`,
    `Binary SHA-256: ${report.engine.sha256}`,
    `Platform: ${report.platform.os}/${report.platform.arch} (${report.platform.headless ? "headless" : "headed"})`,
    "",
  ];
  for (const surface of SURFACES) {
    const item = report.evidence[surface];
    lines.push(`${surface.padEnd(20)} ${item.status.padEnd(8)} ${item.method}`);
  }
  lines.push("", `Native coverage claim: ${report.claims.nativeCoverage}`, report.claims.note);
  return `${lines.join("\n")}\n`;
}
