import type { ProxyCoherenceResult } from "./proxyCoherence";
import type { TargetContext } from "@multizen/cdp-driver";
import type { BrowserEngine } from "@multizen/settings-store";

export type CdpSender = (method: string, params?: Record<string, unknown>) => Promise<unknown>;

export function requireProxyGeolocationCoordinates(
  coordinates: { latitude: number; longitude: number } | null,
): { latitude: number; longitude: number } {
  if (!coordinates) {
    throw new Error("Geolocation protection unavailable; launch blocked");
  }
  return coordinates;
}

export function shouldApplyGeolocationOverride(
  _engine: "cft" | "cloakbrowser",
  ctx: TargetContext,
): boolean {
  return ctx.type === "page";
}

/** Apply the CDP geolocation override and report whether it landed. */
export async function applyGeolocationOverride(
  engine: BrowserEngine,
  send: CdpSender,
  coordinates: { latitude: number; longitude: number },
  coherence?: ProxyCoherenceResult,
): Promise<boolean> {
  try {
    await send("Emulation.setGeolocationOverride", {
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      accuracy: 100,
    });
    return true;
  } catch (error) {
    console.error(`[phantom] ${engine} CDP geolocation override failed:`, error);
    if (coherence) {
      coherence.status = "degraded";
      coherence.geolocationCoverage = "unavailable";
      coherence.issues = [...coherence.issues, "CDP geolocation override failed"];
    }
    throw new Error(`${engine} geolocation protection failed closed`, { cause: error });
  }
}
