import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";

/**
 * Which Chromium-derived binary the bootstrap downloads on first run.
 *   - "cft": Chrome for Testing — Google's official automation channel,
 *     same binary Puppeteer/Playwright use. Stable, reproducible, but
 *     no anti-detect patches (CFT branding, vanilla TLS fingerprint).
 *   - "cloakbrowser": CloakBrowser — Chromium with 50+ source-level
 *     stealth patches (canvas farbling, WebRTC, CDP traces removed).
 *     Drops detection rate against Cloudflare/DataDome/Akamai. Binary
 *     is "free to use, no redistribution" — we auto-download to user
 *     machine, never bundle. Slightly older Mac builds (145 vs 148 CFT).
 */
export type BrowserEngine = "cft" | "cloakbrowser";

export interface AppSettings {
  /** Theme — "dark" only for now, kept for forward compatibility */
  theme: "dark";
  /** Whether to spawn local MCP HTTP server on app start */
  mcpHttpEnabled: boolean;
  /** Port for MCP HTTP server */
  mcpHttpPort: number;
  /** Which Chromium binary to download + run. Switching requires app restart. */
  browserEngine: BrowserEngine;
  /**
   * Automatically check for + (on Windows/Linux) download app updates in the
   * background. On macOS the app can only notify, not auto-install. Manual
   * "Check for updates" works regardless of this flag.
   */
  autoUpdate: boolean;
  /**
   * Opt-in anonymous usage heartbeat. OFF by default — for an anti-detect
   * audience any call-call must be an explicit choice. When on, the app sends
   * at most one ping/day carrying only app version + OS family + an ephemeral
   * single-use nonce — no persistent id, no IP sent. The MULTIZEN_NO_TELEMETRY
   * env var force-disables it regardless. See docs/TELEMETRY.md.
   */
  usageReporting: boolean;

  // ---- Advanced timeouts (milliseconds) ----
  // All exposed in Settings → Advanced so users on slow proxies or slow
  // machines can bump them without editing config files.

  /** Budget for CDP readiness: /json/version → page target → connect+attach.
   *  Default 15s. If Chromium is slow to start (heavy AV scan, cold cache),
   *  bump this to avoid "CDP not ready" launch failures. */
  cdpReadyTimeoutMs: number;
  /** Timeout for proxy geo-location probe during profile launch.
   *  Default 4s. Slow residential proxies may need 8–10s. */
  proxyProbeTimeoutMs: number;
  /** Timeout for proxy geo probe during background country backfill.
   *  Default 6s. Slightly more lenient than the launch-path probe. */
  proxyBackfillTimeoutMs: number;
  /** Grace period for `Browser.close` over CDP before escalating to SIGTERM.
   *  Default 4s. macOS needs ~500ms–2s to flush session-restore. */
  shutdownGraceMs: number;
  /** Budget for SIGTERM → process exit before escalating to SIGKILL.
   *  Default 2s. */
  shutdownSigtermMs: number;
  /** Budget for SIGKILL → confirmed process death.
   *  Default 2s. */
  shutdownSigkillMs: number;
}

const DEFAULTS: AppSettings = {
  theme: "dark",
  mcpHttpEnabled: true,
  mcpHttpPort: 7777,
  // Use Chrome for Testing for the baseline: it is an official, reproducible
  // runtime and avoids silently making a proprietary stealth binary the
  // default before redistribution terms are cleared. CloakBrowser remains an
  // explicit opt-in from Settings for internal evaluation only.
  browserEngine: "cft",
  autoUpdate: true,
  // Opt-in. Never phone home unless the user explicitly turns this on.
  usageReporting: false,
  // Advanced timeouts — see AppSettings docs above.
  cdpReadyTimeoutMs: 15_000,
  proxyProbeTimeoutMs: 4_000,
  proxyBackfillTimeoutMs: 6_000,
  shutdownGraceMs: 4_000,
  shutdownSigtermMs: 2_000,
  shutdownSigkillMs: 2_000,
};

const TIMEOUT_DEFAULTS: Record<string, number> = {
  cdpReadyTimeoutMs: DEFAULTS.cdpReadyTimeoutMs,
  proxyProbeTimeoutMs: DEFAULTS.proxyProbeTimeoutMs,
  proxyBackfillTimeoutMs: DEFAULTS.proxyBackfillTimeoutMs,
  shutdownGraceMs: DEFAULTS.shutdownGraceMs,
  shutdownSigtermMs: DEFAULTS.shutdownSigtermMs,
  shutdownSigkillMs: DEFAULTS.shutdownSigkillMs,
};

export class SettingsStore {
  private readonly jsonPath: string;
  private cache: AppSettings | null = null;

  constructor(jsonPath: string) {
    this.jsonPath = jsonPath;
    mkdirSync(dirname(jsonPath), { recursive: true });
  }

  async load(): Promise<AppSettings> {
    if (this.cache) return this.cache;

    let raw: Partial<AppSettings> = {};
    if (existsSync(this.jsonPath)) {
      try {
        const txt = readFileSync(this.jsonPath, "utf8");
        raw = JSON.parse(txt) as Partial<AppSettings>;
      } catch {
        raw = {};
      }
    }

    const merged: AppSettings = { ...DEFAULTS, ...raw };
    if (merged.browserEngine !== "cft" && merged.browserEngine !== "cloakbrowser") {
      merged.browserEngine = DEFAULTS.browserEngine;
    }
    if (typeof merged.autoUpdate !== "boolean") {
      merged.autoUpdate = DEFAULTS.autoUpdate;
    }
    if (typeof merged.usageReporting !== "boolean") {
      merged.usageReporting = DEFAULTS.usageReporting;
    }
    // Validate timeout settings — clamp to defaults if invalid.
    const mergedRec = merged as unknown as Record<string, unknown>;
    for (const [key, def] of Object.entries(TIMEOUT_DEFAULTS)) {
      const v = mergedRec[key];
      if (typeof v !== "number" || !Number.isFinite(v) || v < 100) {
        mergedRec[key] = def;
      }
    }
    this.cache = merged;
    return merged;
  }

  async update(patch: Partial<AppSettings>): Promise<AppSettings> {
    const current = await this.load();
    const next = { ...current, ...patch };
    this.cache = next;
    writeFileSync(this.jsonPath, JSON.stringify(next, null, 2), "utf8");
    return next;
  }
}

export function defaultSettingsPath(userDataDir: string): string {
  return join(userDataDir, "settings.json");
}
