export interface SessionStartupPlan {
  writeRestorePreference: boolean;
  restoreLastSession: boolean;
  openStartPage: boolean;
}

export function sessionStartupPlan(hasRestorableSession: boolean): SessionStartupPlan {
  return {
    // Do not rewrite restore preferences on first launch. A forced restore
    // preference can make Chromium open its default window in addition to the
    // positional start URL.
    writeRestorePreference: hasRestorableSession,
    restoreLastSession: hasRestorableSession,
    openStartPage: !hasRestorableSession,
  };
}
