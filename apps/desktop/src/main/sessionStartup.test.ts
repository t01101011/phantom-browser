import assert from "node:assert/strict";
import test from "node:test";
import { sessionStartupPlan } from "./sessionStartup.ts";

test("first launch opens only the configured start page", () => {
  assert.deepEqual(sessionStartupPlan(false), {
    writeRestorePreference: false,
    restoreLastSession: false,
    openStartPage: true,
  });
});

test("returning launch restores session without adding a start page", () => {
  assert.deepEqual(sessionStartupPlan(true, false), {
    writeRestorePreference: true,
    restoreLastSession: true,
    openStartPage: false,
  });
});

test("a changed start page overrides one returning launch instead of restoring the stale tab", () => {
  assert.deepEqual(sessionStartupPlan(true, true), {
    writeRestorePreference: false,
    restoreLastSession: false,
    openStartPage: true,
  });
});
