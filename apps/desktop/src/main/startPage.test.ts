import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_START_URL, sanitizeStartUrl, shouldApplyStartUrl } from "./startPage.ts";

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

test("applies an explicit start page until that exact value has launched", () => {
  assert.equal(shouldApplyStartUrl("google.com", undefined), true);
  assert.equal(shouldApplyStartUrl("google.com", "https://duckduckgo.com/"), true);
  assert.equal(shouldApplyStartUrl("google.com", "https://google.com/"), false);
});

test("does not force the default start page over an existing session", () => {
  assert.equal(shouldApplyStartUrl(undefined, undefined), false);
  assert.equal(shouldApplyStartUrl("", "https://google.com/"), false);
});
