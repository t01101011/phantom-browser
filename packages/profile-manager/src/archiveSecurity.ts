const HEADER_BYTES = 6 + 16 + 12;
const AUTH_TAG_BYTES = 16;
export const MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024;

export function assertExportPassphrase(passphrase: string): void {
  if (passphrase.length < 12) {
    throw new Error("Archive passphrase must be at least 12 characters.");
  }
}

export function assertArchiveByteLength(length: number): void {
  if (!Number.isSafeInteger(length) || length < HEADER_BYTES + AUTH_TAG_BYTES + 4) {
    throw new Error("Archive is truncated.");
  }
  if (length > MAX_ARCHIVE_BYTES) {
    throw new Error("Archive is too large.");
  }
}

export function readFrameLength(
  plaintext: Buffer,
  cursor: number,
  maxLength: number,
): { length: number; nextCursor: number } {
  if (!Number.isSafeInteger(cursor) || cursor < 0 || cursor + 4 > plaintext.length) {
    throw new Error("Archive frame header exceeds authenticated payload.");
  }
  const length = plaintext.readUInt32BE(cursor);
  if (length > maxLength) {
    throw new Error("Archive frame exceeds its policy limit.");
  }
  const nextCursor = cursor + 4;
  if (nextCursor + length > plaintext.length) {
    throw new Error("Archive frame exceeds authenticated payload.");
  }
  return { length, nextCursor };
}
