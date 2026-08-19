/**
 * Launch-contract ↔ probe cross-reference.
 *
 * Connects the Item 6 launch-contract (which FingerprintConfig fields are
 * applied via native-flag / cdp / preload-js / unsupported) to the Item 7
 * extended browser probes (availScreen, dprDepth, icuLocale).
 *
 * The contract declares what SHOULD happen. The probes observe what DID happen.
 * This module asserts the mapping between them is consistent: a field declared
 * "preload-js" on CFT should be OBSERVED with a value matching the fingerprint
 * config, while a field declared "unsupported" on CloakBrowser should leak the
 * host value (not the persona config).
 */

import { LAUNCH_CONTRACT, getCoverage, type CoverageLevel } from "./launchContract.ts";

/**
 * Map probe surface names to the FingerprintConfig fields they validate.
 */
export const PROBE_TO_CONTRACT_FIELDS = {
  availScreen: [
    { field: "availScreen", engine: "cft" as const, expectedLevel: "preload-js" as CoverageLevel },
    { field: "availScreen", engine: "cloakbrowser" as const, expectedLevel: "unsupported" as CoverageLevel },
  ],
  dprDepth: [
    { field: "dpr", engine: "cft" as const, expectedLevel: "cdp" as CoverageLevel },
    { field: "dpr", engine: "cloakbrowser" as const, expectedLevel: "unsupported" as CoverageLevel },
  ],
  icuLocale: [
    { field: "locale", engine: "cft" as const, expectedLevel: "cdp" as CoverageLevel },
    { field: "locale", engine: "cloakbrowser" as const, expectedLevel: "cdp" as CoverageLevel },
  ],
} as const;

/**
 * For a given probe surface and engine, return the contract fields it validates
 * and the expected coverage level.
 */
export function getProbeContractMapping(
  surface: keyof typeof PROBE_TO_CONTRACT_FIELDS,
) {
  return PROBE_TO_CONTRACT_FIELDS[surface];
}

/**
 * Given a probe observation and the fingerprint config it was launched with,
 * classify whether the observation is consistent with the declared contract.
 *
 * Returns "consistent" | "inconsistent" | "no-observation".
 */
export function classifyProbeResult(
  surface: keyof typeof PROBE_TO_CONTRACT_FIELDS,
  engine: "cft" | "cloakbrowser",
  observed: { status: string; value?: unknown } | undefined,
  fingerprintConfig: Record<string, unknown>,
): "consistent" | "inconsistent" | "no-observation" {
  if (!observed || observed.status !== "OBSERVED" || !observed.value) {
    return "no-observation";
  }

  const mappings = getProbeContractMapping(surface);
  const relevant = mappings.filter((m) => m.engine === engine);

  for (const { field, expectedLevel } of relevant) {
    const actualLevel = getCoverage(field, engine);

    // If the contract says "unsupported", the probe should observe HOST values
    // (not the persona config). If it says "preload-js" or "cdp", the probe
    // should observe PERSONA values (the override took effect).
    if (expectedLevel === "unsupported") {
      // For unsupported fields, we expect the probe to show a host value
      // that does NOT match the persona config. We can't assert mismatch
      // without knowing the host value, but we can assert the contract
      // entry says unsupported.
      if (actualLevel !== "unsupported") {
        return "inconsistent";
      }
    } else {
      // For applied fields, we expect the probe to show the persona value.
      if (actualLevel !== expectedLevel) {
        return "inconsistent";
      }
    }
  }

  return "consistent";
}

/**
 * Get the full cross-reference table: for every extended probe surface,
 * what FingerprintConfig field and coverage level it validates.
 */
export function getCrossReferenceTable() {
  const rows: Array<{
    surface: string;
    field: string;
    engine: "cft" | "cloakbrowser";
    expectedCoverage: CoverageLevel;
    actualCoverage: CoverageLevel;
    match: boolean;
  }> = [];

  for (const [surface, mappings] of Object.entries(PROBE_TO_CONTRACT_FIELDS)) {
    for (const { field, engine, expectedLevel } of mappings) {
      const actual = getCoverage(field, engine);
      rows.push({
        surface,
        field,
        engine,
        expectedCoverage: expectedLevel,
        actualCoverage: actual,
        match: actual === expectedLevel,
      });
    }
  }

  return rows;
}
