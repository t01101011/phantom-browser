import type { ProxyCoherenceResult } from "./proxyCoherence";
import type { TargetContext } from "@multizen/cdp-driver";

export type CdpSender = (method: string, params?: Record<string, unknown>) => Promise<unknown>;

export function shouldApplyCftGeolocationOverride(ctx: TargetContext): boolean {
  return ctx.type === "page";
}

/** Apply CFT's weaker CDP geolocation fallback and report whether it landed. */
export async function applyCftGeolocationOverride(
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
    console.error("[phantom] CFT CDP geolocation fallback failed:", error);
    if (coherence) {
      coherence.status = "degraded";
      coherence.geolocationCoverage = "unavailable";
      coherence.issues = [...coherence.issues, "CFT CDP geolocation fallback failed"];
    }
    return false;
  }
}
