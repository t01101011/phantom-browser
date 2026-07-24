import assert from "node:assert/strict";
import test from "node:test";
import {
  assertExportPassphrase,
  assertArchiveByteLength,
  readFrameLength,
} from "../src/archiveSecurity.ts";

test("export rejects passphrases shorter than 12 characters", () => {
  assert.throws(() => assertExportPassphrase("short123"), /at least 12 characters/i);
  assert.doesNotThrow(() => assertExportPassphrase("correct-horse"));
});

test("archive input rejects truncated and oversized files before decryption", () => {
  assert.throws(() => assertArchiveByteLength(5), /truncated/i);
  assert.throws(() => assertArchiveByteLength(Number.MAX_SAFE_INTEGER), /too large/i);
});

test("frame reader rejects lengths outside the remaining authenticated plaintext", () => {
  const plaintext = Buffer.alloc(8);
  plaintext.writeUInt32BE(20, 0);
  assert.throws(() => readFrameLength(plaintext, 0, 16), /exceeds/i);
});

test("frame reader rejects declared entries above their policy limit", () => {
  const plaintext = Buffer.alloc(8);
  plaintext.writeUInt32BE(7, 0);
  assert.throws(() => readFrameLength(plaintext, 0, 6), /limit/i);
});
