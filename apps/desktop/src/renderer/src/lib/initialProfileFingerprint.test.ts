import assert from "node:assert/strict";
import test from "node:test";
import { initialProfileFingerprint } from "./initialProfileFingerprint.ts";

const generated = {
  locale: "ms-MY",
  timezone: "Asia/Kuala_Lumpur",
} as never;
const reconciled = {
  locale: "en-US",
  timezone: "America/New_York",
} as never;

test("new profiles start with a predictable en-US locale", async () => {
  const calls: unknown[] = [];
  const result = await initialProfileFingerprint(
    async () => generated,
    async (fp, patch) => {
      calls.push([fp, patch]);
      return reconciled;
    },
  );

  assert.equal(result, reconciled);
  assert.deepEqual(calls, [[generated, { localeId: "en-US", timezone: "America/New_York" }]]);
});
