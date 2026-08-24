import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { discardRestorableSession, sessionStartupPlan } from "./sessionStartup.ts";

test("first launch opens only the configured start page", () => {
  assert.deepEqual(sessionStartupPlan(false), {
    restoreLastSession: false,
    openStartPage: true,
  });
});

test("returning launch restores session without adding a start page", () => {
  assert.deepEqual(sessionStartupPlan(true, false), {
    restoreLastSession: true,
    openStartPage: false,
  });
});

test("a changed start page overrides one returning launch instead of restoring the stale tab", () => {
  assert.deepEqual(sessionStartupPlan(true, true), {
    restoreLastSession: false,
    openStartPage: true,
  });
});

test("changed start page atomically removes legacy and modern restorable session state", async () => {
  const root = await mkdtemp(join(tmpdir(), "phantom-session-reset-"));
  const profile = join(root, "Default");
  await mkdir(join(profile, "Sessions"), { recursive: true });
  await writeFile(join(profile, "Sessions", "Tabs_1"), "modern");
  await writeFile(join(profile, "Current Session"), "legacy");
  try {
    await discardRestorableSession(root);
    await assert.rejects(readFile(join(profile, "Sessions", "Tabs_1")), /ENOENT/);
    await assert.rejects(readFile(join(profile, "Current Session")), /ENOENT/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
