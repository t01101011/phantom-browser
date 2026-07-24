import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_START_URL, sanitizeStartUrl } from "./startPage.ts";

test("adds https to a schemeless start page entered in the profile UI", () => {
  assert.equal(sanitizeStartUrl("google.com"), "https://google.com/");
});

test("keeps an explicit safe start page URL", () => {
  assert.equal(sanitizeStartUrl("https://example.com/path?q=1"), "https://example.com/path?q=1");
});

test("falls back for unsafe or malformed values", () => {
  assert.equal(sanitizeStartUrl("--remote-debugging-port=9222"), DEFAULT_START_URL);
  assert.equal(sanitizeStartUrl("javascript:alert(1)"), DEFAULT_START_URL);
  assert.equal(sanitizeStartUrl("not a host"), DEFAULT_START_URL);
});
