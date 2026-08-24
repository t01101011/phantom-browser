import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import type { Agent } from "node:http";
import { isIP } from "node:net";
import { HttpsProxyAgent } from "https-proxy-agent";
import { SocksProxyAgent } from "socks-proxy-agent";
import type { ProxyConfig } from "@multizen/types";

/**
 * Result of probing a proxy for its public IP geolocation.
 *
 * Used to verify that a profile's locale + timezone are coherent with the
 * proxy IP's country — detection vendors flag mismatches like
 * "Accept-Language: ru-RU + IP in US".
 */
export interface ProxyGeoResult {
  country: string;
  countryName: string;
  timezone: string;
  city: string;
  ip: string;
  /** Egress IP coordinates — fed into CloakBrowser's --fingerprint-location
   *  so navigator.geolocation reports the proxy's geo, matching the IP. */
  latitude?: number;
  longitude?: number;
}

// ── Provider definitions ───────────────────────────────────────────────

/** A geo-IP provider that can be probed through a proxy. */
interface GeoProvider {
  name: string;
  url: string;
  /** Build anormalized ProxyGeoResult from the raw JSON payload. */
  parse: (raw: unknown) => ProxyGeoResult;
}

/**
 * Multi-provider proxy geo probe. Tries each provider in order until one
 * succeeds. This fixes persistent 429 rate-limiting from ipapi.co when
 * testing multiple profiles in quick succession.
 *
 * Provider order (by rate-limit generosity):
 *  1. ipwho.is — HTTPS, 10k/month, rarely rate-limits
 *  2. ipapi.co  — HTTPS, 1k/day, frequently 429
 *  3. ip-api.com — HTTP only on free tier, 45 req/min (fallback of last resort)
 */
const PROVIDERS: GeoProvider[] = [
  {
    name: "ipwho.is",
    url: "https://ipwho.is/",
    parse: parseIpwho,
  },
  {
    name: "ipapi.co",
    url: "https://ipapi.co/json/",
    parse: parseIpapi,
  },
];

// ── Public API ─────────────────────────────────────────────────────────

/**
 * Probe the proxy's exit IP geolocation. Uses multi-provider fallback to
 * avoid 429 rate-limit failures.
 */
export async function probeProxyGeo(
  proxy: ProxyConfig,
  opts: {
    timeoutMs?: number;
    requestJson?: (proxy: ProxyConfig, timeoutMs: number) => Promise<unknown>;
    /** Test seams for deterministic absolute-deadline coverage. */
    now?: () => number;
    fetchJson?: (url: string, proxy: ProxyConfig, timeoutMs: number) => Promise<unknown>;
  } = {},
): Promise<ProxyGeoResult> {
  // If a custom requestJson is injected (for testing), use the legacy
  // ipapi.co parse path so existing tests continue to work unchanged.
  if (opts.requestJson) {
    const json = await opts.requestJson(proxy, opts.timeoutMs ?? 10000);
    return parseProxyGeoPayload(json as RawIpapi);
  }

  const timeoutMs = opts.timeoutMs ?? 10000;
  const now = opts.now ?? Date.now;
  const fetchJson = opts.fetchJson ?? fetchThroughProxy;
  const deadline = now() + timeoutMs;
  const errors: string[] = [];

  for (const provider of PROVIDERS) {
    const remaining = deadline - now();
    if (remaining <= 0) {
      errors.push(`${provider.name}: skipped (probe deadline reached)`);
      break;
    }
    try {
      const raw = await fetchJson(provider.url, proxy, remaining);
      return provider.parse(raw);
    } catch (err) {
      const msg = (err as Error).message;
      // Don't log credentials — errors from fetchThroughProxy already
      // sanitize proxy details.
      errors.push(`${provider.name}: ${msg}`);
    }
  }

  throw new Error(`All geo-IP providers failed — ${errors.join("; ")}`);
}

// ── Legacy type + parser (kept for test compatibility) ──────────────────

export interface RawIpapi {
  ip: string;
  city: string;
  country_code: string;
  country_name: string;
  timezone: string;
  latitude?: number;
  longitude?: number;
  error?: boolean;
  reason?: string;
}

/** Legacy parser — used when requestJson is injected (tests). */
export function parseProxyGeoPayload(json: RawIpapi): ProxyGeoResult {
  if (!json.country_code || !json.timezone) {
    if (json.error) {
      throw new Error(`ipapi.co error: ${json.reason ?? "rate-limit or block"}`);
    }
    throw new Error("ipapi.co returned an unexpected payload");
  }
  if (isIP(json.ip ?? "") === 0) {
    throw new Error("ipapi.co returned no valid egress IP");
  }

  return {
    country: json.country_code.toLowerCase(),
    countryName: json.country_name ?? json.country_code,
    timezone: json.timezone,
    city: json.city ?? "",
    ip: json.ip,
    latitude: typeof json.latitude === "number" ? json.latitude : undefined,
    longitude: typeof json.longitude === "number" ? json.longitude : undefined,
  };
}

// ── Provider parsers ───────────────────────────────────────────────────

/** Parse ipapi.co JSON response. */
function parseIpapi(raw: unknown): ProxyGeoResult {
  const json = raw as RawIpapi;
  if (!json.country_code || !json.timezone) {
    if (json.error) {
      throw new Error(`ipapi.co error: ${json.reason ?? "rate-limit or block"}`);
    }
    throw new Error("ipapi.co returned an unexpected payload");
  }
  if (isIP(json.ip ?? "") === 0) {
    throw new Error("ipapi.co returned no valid egress IP");
  }
  return {
    country: json.country_code.toLowerCase(),
    countryName: json.country_name ?? json.country_code,
    timezone: json.timezone,
    city: json.city ?? "",
    ip: json.ip,
    latitude: typeof json.latitude === "number" ? json.latitude : undefined,
    longitude: typeof json.longitude === "number" ? json.longitude : undefined,
  };
}

/** Parse ipwho.is JSON response. */
interface RawIpwho {
  ip?: string;
  city?: string;
  country_code?: string;
  country?: string;
  timezone?: { id?: string };
  latitude?: number;
  longitude?: number;
  success?: boolean;
  message?: string;
}

function parseIpwho(raw: unknown): ProxyGeoResult {
  const json = raw as RawIpwho;
  if (!json.success && json.message) {
    throw new Error(`ipwho.is error: ${json.message}`);
  }
  if (!json.country_code) {
    throw new Error("ipwho.is returned an unexpected payload");
  }
  if (isIP(json.ip ?? "") === 0) {
    throw new Error("ipwho.is returned no valid egress IP");
  }
  return {
    country: json.country_code.toLowerCase(),
    countryName: json.country ?? json.country_code,
    timezone: json.timezone?.id ?? "",
    city: json.city ?? "",
    ip: json.ip!,
    latitude: typeof json.latitude === "number" ? json.latitude : undefined,
    longitude: typeof json.longitude === "number" ? json.longitude : undefined,
  };
}

// ── HTTP fetch through proxy ────────────────────────────────────────────

/**
 * Fetch JSON from a URL through the supplied proxy. Uses Node's built-in
 * `https.request` with `https-proxy-agent` / `socks-proxy-agent` (Electron's
 * bundled Node lacks the latest undici APIs).
 */
async function fetchThroughProxy(
  url: string,
  proxy: ProxyConfig,
  timeoutMs: number,
): Promise<unknown> {
  const proxyUrl = buildProxyUrl(proxy);
  const agent =
    proxy.type === "socks5" ? new SocksProxyAgent(proxyUrl) : new HttpsProxyAgent(proxyUrl);

  return fetchJsonWithAbsoluteDeadline(url, agent, timeoutMs);
}

export function fetchJsonWithAbsoluteDeadline(
  url: string,
  agent: Agent | undefined,
  timeoutMs: number,
  maxResponseBytes = 256 * 1024,
): Promise<unknown> {
  return new Promise<unknown>((resolve, reject) => {
    let settled = false;
    const finish = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      clearTimeout(deadlineTimer);
      fn();
    };
    const requestForUrl = new URL(url).protocol === "http:" ? httpRequest : httpsRequest;
    const req = requestForUrl(
      url,
      {
        agent,
        method: "GET",
        headers: {
          "user-agent": "PhantomBrowser/0.4 (proxy-geo-probe)",
          accept: "application/json",
        },
      },
      (res) => {
        if (!res.statusCode || res.statusCode >= 400) {
          const error = new Error(`HTTP ${res.statusCode}`);
          finish(() => reject(error));
          res.destroy(error);
          req.destroy(error);
          return;
        }
        const chunks: Buffer[] = [];
        let received = 0;
        res.on("data", (c: Buffer) => {
          received += c.length;
          if (received > maxResponseBytes) {
            const error = new Error("proxy probe response too large");
            finish(() => reject(error));
            res.destroy();
            req.destroy();
            return;
          }
          chunks.push(c);
        });
        res.on("end", () => {
          try {
            const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
            finish(() => resolve(parsed));
          } catch (e) {
            finish(() => reject(new Error(`invalid JSON: ${(e as Error).message}`)));
          }
        });
        res.on("error", (error) => finish(() => reject(error)));
      },
    );
    const deadlineTimer = setTimeout(() => {
      req.destroy(new Error("proxy probe timed out"));
    }, timeoutMs);
    req.on("error", (error) => finish(() => reject(error)));
    req.end();
  });
}

// ── Utils ───────────────────────────────────────────────────────────────

function buildProxyUrl(p: ProxyConfig): string {
  const auth =
    p.username && p.password
      ? `${encodeURIComponent(p.username)}:${encodeURIComponent(p.password)}@`
      : p.username
        ? `${encodeURIComponent(p.username)}@`
        : "";
  const scheme = p.type === "socks5" ? "socks5" : "http";
  return `${scheme}://${auth}${p.host}:${p.port}`;
}
