import assert from "node:assert/strict";
import test from "node:test";
import { parseChromiumVersion } from "./chromiumVersion.ts";

test("parses a ready bootstrap version without launching the browser binary", () => {
  assert.deepEqual(parseChromiumVersion("146.0.7680.177"), {
    major: 146,
    full: "146.0.7680.177",
  });
});

test("rejects non-four-part versions", () => {
  assert.equal(parseChromiumVersion(undefined), null);
  assert.equal(parseChromiumVersion("Stable"), null);
});
