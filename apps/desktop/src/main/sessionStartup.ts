import { rename, rm } from "node:fs/promises";
import { join } from "node:path";

export interface SessionStartupPlan {
  restoreLastSession: boolean;
  openStartPage: boolean;
}

export function sessionStartupPlan(
  hasRestorableSession: boolean,
  startPageChanged = false,
): SessionStartupPlan {
  const restoreSession = hasRestorableSession && !startPageChanged;
  return {
    restoreLastSession: restoreSession,
    openStartPage: !restoreSession,
  };
}

/**
 * Discard saved tabs before Chromium starts, so a changed start page cannot
 * execute restored content before fail-closed target protection is installed.
 * Rename first: Chromium never observes a partially removed Sessions tree.
 */
export async function discardRestorableSession(dataDir: string): Promise<void> {
  const profileDir = join(dataDir, "Default");
  const candidates = ["Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs"];
  for (const name of candidates) {
    const source = join(profileDir, name);
    const tombstone = join(
      profileDir,
      `.phantom-discarded-${name.replaceAll(" ", "-")}-${Date.now()}`,
    );
    try {
      await rename(source, tombstone);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") continue;
      throw error;
    }
    await rm(tombstone, { recursive: true, force: true });
  }
}
