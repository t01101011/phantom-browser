export interface SessionStartupPlan {
  writeRestorePreference: boolean;
  writeStartPagePreference: boolean;
  restoreLastSession: boolean;
  openStartPage: boolean;
}

export function sessionStartupPlan(
  hasRestorableSession: boolean,
  startPageChanged = false,
): SessionStartupPlan {
  const restoreSession = hasRestorableSession && !startPageChanged;
  return {
    // Do not rewrite restore preferences on first launch. A forced restore
    // preference can make Chromium open its default window in addition to the
    // positional start URL.
    writeRestorePreference: restoreSession,
    writeStartPagePreference: hasRestorableSession && startPageChanged,
    restoreLastSession: restoreSession,
    openStartPage: !restoreSession,
  };
}
