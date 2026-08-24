import assert from "node:assert/strict";
import test from "node:test";
// Node's strip-types runner resolves the source file directly in this test.
// @ts-expect-error TS5097: runtime test imports the adjacent TypeScript source.
import { CdpSession, type TargetContext, type TargetSender } from "./CdpSession.ts";

type Attached = {
  sessionId: string;
  targetInfo: { targetId: string; type: string };
};

function harness(opts: { onProtectionFailure?: (error: unknown) => Promise<void> | void } = {}) {
  let attached: ((params: Attached) => void) | undefined;
  const calls: string[] = [];
  const client = {
    Target: {
      setAutoAttach: async () => {
        calls.push("auto-attach");
      },
      getTargets: async () => {
        calls.push("enumerate");
        return { targetInfos: [] };
      },
      attachToTarget: async () => ({ sessionId: "existing-session" }),
    },
    on: (event: string, cb: (params: Attached) => void) => {
      if (event === "Target.attachedToTarget") attached = cb;
    },
    send: async (method: string) => {
      calls.push(method);
    },
    close: async () => {
      calls.push("session-close");
    },
  };
  const session = new CdpSession({
    port: 9222,
    protectionFailureTimeoutMs: 5,
    onProtectionFailure: opts.onProtectionFailure,
  });
  (session as unknown as { client: unknown }).client = client;
  return { session, calls, emit: (params: Attached) => attached?.(params) };
}

test("auto-attach is armed before enumeration and duplicate future delivery configures once", async () => {
  const h = harness();
  let setups = 0;
  await h.session.bootstrapTargets(async (_send: TargetSender, ctx: TargetContext) => {
    if (!ctx.isRoot) setups += 1;
  });
  assert.ok(h.calls.indexOf("auto-attach") < h.calls.indexOf("enumerate"));

  const event = { sessionId: "s1", targetInfo: { targetId: "page-1", type: "page" } };
  h.emit(event);
  h.emit(event);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(setups, 1);
  assert.equal(h.calls.filter((x) => x === "Runtime.runIfWaitingForDebugger").length, 2);
});

test("future-target setup rejection reaches bounded external fail-closed shutdown", async () => {
  const failures: unknown[] = [];
  const h = harness({
    onProtectionFailure: async (error) => {
      failures.push(error);
    },
  });
  h.session.closeBrowser = () => new Promise(() => {});
  await h.session.bootstrapTargets(async (_send, ctx) => {
    if (!ctx.isRoot) throw new Error("override rejected");
  });

  h.emit({ sessionId: "s2", targetInfo: { targetId: "page-2", type: "page" } });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(failures.length, 1);
  assert.match(String(failures[0]), /override rejected/);
  assert.ok(h.calls.includes("session-close"));
});

test("duplicate failed future-target delivery triggers owner cleanup exactly once", async () => {
  let ownerCleanups = 0;
  const h = harness({
    onProtectionFailure: async () => {
      ownerCleanups += 1;
    },
  });
  await h.session.bootstrapTargets(async (_send, ctx) => {
    if (!ctx.isRoot) throw new Error("override rejected");
  });

  const event = { sessionId: "s3", targetInfo: { targetId: "page-3", type: "page" } };
  h.emit(event);
  h.emit(event);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(ownerCleanups, 1);
});
