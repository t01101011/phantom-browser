import assert from "node:assert/strict";
import test from "node:test";
import { cleanupFailedBrowserLaunch } from "./launchFailureCleanup.ts";

test("failed protection bootstrap kills the untracked browser before stopping its proxy bridge", async () => {
  const calls: string[] = [];

  await cleanupFailedBrowserLaunch({
    killChild: () => {
      calls.push("kill-child");
    },
    closeSession: async () => {
      calls.push("close-session");
    },
    killUsingDataDir: async () => {
      calls.push("kill-data-dir");
    },
    stopBridge: async () => {
      calls.push("stop-bridge");
    },
  });

  assert.deepEqual(calls, ["kill-child", "close-session", "kill-data-dir", "stop-bridge"]);
});

test("failure after bridge acquisition but before spawn still stops the bridge", async () => {
  const calls: string[] = [];

  await cleanupFailedBrowserLaunch({
    stopBridge: async () => {
      calls.push("stop-bridge");
    },
  });

  assert.deepEqual(calls, ["stop-bridge"]);
});

test("failed-launch cleanup continues after an earlier cleanup step rejects", async () => {
  const calls: string[] = [];

  await cleanupFailedBrowserLaunch({
    killChild: () => {
      calls.push("kill-child");
      throw new Error("kill failed");
    },
    closeSession: async () => {
      calls.push("close-session");
      throw new Error("close failed");
    },
    killUsingDataDir: async () => {
      calls.push("kill-data-dir");
    },
    stopBridge: async () => {
      calls.push("stop-bridge");
    },
  });

  assert.deepEqual(calls, ["kill-child", "close-session", "kill-data-dir", "stop-bridge"]);
});

test("failed-launch cleanup does not wait forever for a hung session close", async () => {
  const calls: string[] = [];

  await cleanupFailedBrowserLaunch(
    {
      closeSession: () => new Promise(() => {}),
      killUsingDataDir: async () => {
        calls.push("kill-data-dir");
      },
      stopBridge: async () => {
        calls.push("stop-bridge");
      },
    },
    5,
  );

  assert.deepEqual(calls, ["kill-data-dir", "stop-bridge"]);
});
