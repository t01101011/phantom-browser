import type { FingerprintConfig } from "../types";

const DEFAULT_LOCALE = "en-US";
const DEFAULT_TIMEZONE = "America/New_York";

export async function initialProfileFingerprint(
  generate: () => Promise<FingerprintConfig>,
  reconcile: (
    current: FingerprintConfig,
    patch: { localeId: string; timezone: string },
  ) => Promise<FingerprintConfig>,
): Promise<FingerprintConfig> {
  const generated = await generate();
  return reconcile(generated, {
    localeId: DEFAULT_LOCALE,
    timezone: DEFAULT_TIMEZONE,
  });
}
