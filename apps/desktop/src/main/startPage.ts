/**
 * Per-profile start page helpers (opened on a profile's first launch).
 *
 * NOTE: a per-profile default-search-engine feature was prototyped alongside
 * this, but ungoogled CloakBrowser ignores both pref-seeding and extension
 * `search_provider` overrides (verified on the real binary — see
 * specs/profile-startpage-search). Default search is therefore deferred to the
 * patched-Chromium build; only the start page ships for now.
 */

/** Opened on a profile's first launch when it has no explicit `startUrl`. */
export const DEFAULT_START_URL = "https://duckduckgo.com/";

/**
 * Sanitize a profile's start URL into a safe positional Chromium arg. Only
 * http(s) and about: URLs are allowed. A hostname entered without a scheme
 * (for example `google.com`) is normalized to HTTPS. Anything else (empty,
 * malformed text, or a `-`/`--`-prefixed token that Chromium would parse as a
 * command-line switch) falls back to the default. This closes an arg-injection
 * surface — the value can be set by MCP agents, and Chromium's CommandLine
 * treats any leading-dash token as a switch regardless of argv position.
 */
export function sanitizeStartUrl(raw?: string): string {
  return normalizeExplicitStartUrl(raw) ?? DEFAULT_START_URL;
}

export function shouldApplyStartUrl(raw: string | undefined, lastApplied: string | undefined): boolean {
  const normalized = normalizeExplicitStartUrl(raw);
  return normalized !== null && normalized !== lastApplied;
}

function normalizeExplicitStartUrl(raw?: string): string | null {
  const v = (raw ?? "").trim();
  if (!v || v.startsWith("-")) return null;

  const candidates = /^[a-z][a-z\d+.-]*:/i.test(v) ? [v] : [`https://${v}`];
  for (const candidate of candidates) {
    try {
      const u = new URL(candidate);
      if (
        (u.protocol === "http:" || u.protocol === "https:") &&
        u.hostname.includes(".")
      ) {
        return u.href;
      }
      if (u.protocol === "about:" && candidate === v) return v;
    } catch {
      // Try the next candidate, then reject the explicit value.
    }
  }
  return null;
}
