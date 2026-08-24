export interface FailedBrowserLaunchCleanup {
  killChild?: () => void;
  closeSession?: () => Promise<void>;
  killUsingDataDir?: () => Promise<void>;
  stopBridge: () => Promise<void>;
}

/** Best-effort teardown for a browser that failed before it entered the running map. */
export async function cleanupFailedBrowserLaunch(
  cleanup: FailedBrowserLaunchCleanup,
  stepTimeoutMs = 1000,
): Promise<void> {
  try {
    cleanup.killChild?.();
  } catch {
    // Continue to the data-dir sweep; the direct child may already be gone.
  }
  await boundedCleanup(cleanup.closeSession, stepTimeoutMs);
  await boundedCleanup(cleanup.killUsingDataDir, stepTimeoutMs);
  await boundedCleanup(cleanup.stopBridge, stepTimeoutMs);
}

async function boundedCleanup(
  step: (() => Promise<void>) | undefined,
  timeoutMs: number,
): Promise<void> {
  if (!step) return;
  let timer: NodeJS.Timeout | undefined;
  await Promise.race([
    Promise.resolve()
      .then(step)
      .catch(() => {}),
    new Promise<void>((resolve) => {
      timer = setTimeout(resolve, timeoutMs);
    }),
  ]).finally(() => {
    if (timer) clearTimeout(timer);
  });
}
