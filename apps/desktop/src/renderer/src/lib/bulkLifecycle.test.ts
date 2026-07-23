import assert from "node:assert/strict";
import test from "node:test";
import { runBulkLifecycle } from "./bulkLifecycle.ts";

test("bulk lifecycle deduplicates ids and preserves successful work when one action fails", async () => {
  const calls: string[] = [];
  const result = await runBulkLifecycle(["a", "bad", "a", "c"], async (id) => {
    calls.push(id);
    if (id === "bad") throw new Error("proxy unavailable");
  });

  assert.deepEqual(calls.sort(), ["a", "bad", "c"]);
  assert.deepEqual(result.succeeded.sort(), ["a", "c"]);
  assert.deepEqual(result.failed, [{ id: "bad", error: "proxy unavailable" }]);
});

test("bulk lifecycle handles non-Error failures", async () => {
  const result = await runBulkLifecycle(["x"], async () => {
    throw "stopped";
  });

  assert.deepEqual(result, {
    succeeded: [],
    failed: [{ id: "x", error: "stopped" }],
  });
});
