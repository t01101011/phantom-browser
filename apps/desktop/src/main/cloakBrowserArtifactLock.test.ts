import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  CLOAKBROWSER_CACHE_AUTH_SCHEMA_VERSION,
  CLOAKBROWSER_ENGINE_LOCK,
  resolveLockedCloakBrowserArtifact,
  resolveContainedRegularFile,
  validateCloakBrowserCacheAuthentication,
  verifySignedCloakBrowserManifest,
  type CloakBrowserEngineLock,
  type CloakBrowserPlatformLock,
} from "./cloakBrowserArtifactLock.ts";

const TEST_ARTIFACT: CloakBrowserPlatformLock = {
  releaseTag: "chromium-v146.0.7680.177.5",
  chromiumVersion: "146.0.7680.177.5",
  assetFilename: "cloakbrowser-linux-x64.tar.gz",
  sha256: "4a12bcde95fa1bb1beef2b41ab5e5c27c36be78e3be3d0dac8c64d705216670e",
  channel: "free-public",
  license: "proprietary-binary-separate-license",
};

test("selects the exact locked artifact for the requested platform", () => {
  assert.deepEqual(resolveLockedCloakBrowserArtifact("linux", "x64"), TEST_ARTIFACT);
  assert.equal(
    CLOAKBROWSER_ENGINE_LOCK.upstreamWrapperRevision,
    "a5f2c33ff9aa27cabd93871d714ee1469fb8fcc5",
  );
});

test("fails closed when the engine lock has no requested platform", () => {
  assert.throws(
    () => resolveLockedCloakBrowserArtifact("freebsd", "x64"),
    /has no artifact.*refusing to select another release/,
  );
});

test("does not fall back to another platform or release", () => {
  const onePlatformLock: CloakBrowserEngineLock = {
    ...CLOAKBROWSER_ENGINE_LOCK,
    platforms: { "linux-x64": TEST_ARTIFACT },
  };
  assert.throws(
    () => resolveLockedCloakBrowserArtifact("win32", "x64", onePlatformLock),
    /no artifact for win32-x64/,
  );
});

test("accepts an Ed25519-signed manifest bound to the locked version and checksum", () => {
  const signed = signedManifest(TEST_ARTIFACT);
  assert.doesNotThrow(() =>
    verifySignedCloakBrowserManifest(
      signed.manifest,
      signed.signature,
      TEST_ARTIFACT,
      signed.publicKey,
    ),
  );
});

test("rejects a signed checksum that differs from the engine lock", () => {
  const signed = signedManifest({
    ...TEST_ARTIFACT,
    sha256: "0".repeat(64),
  });
  assert.throws(
    () =>
      verifySignedCloakBrowserManifest(
        signed.manifest,
        signed.signature,
        TEST_ARTIFACT,
        signed.publicKey,
      ),
    /does not match the engine lock/,
  );
});

test("rejects a manifest whose signature does not authenticate", () => {
  const signed = signedManifest(TEST_ARTIFACT);
  signed.manifest[0] = (signed.manifest[0] ?? 0) ^ 1;
  assert.throws(
    () =>
      verifySignedCloakBrowserManifest(
        signed.manifest,
        signed.signature,
        TEST_ARTIFACT,
        signed.publicKey,
      ),
    /signature verification failed/,
  );
});

test("rejects a matching legacy cache without authenticated-manifest attestation", () => {
  assert.throws(
    () => validateCloakBrowserCacheAuthentication(undefined, TEST_ARTIFACT),
    /lacks authenticated-manifest attestation/,
  );
});

test("accepts cache attestation bound to the signed manifest, publisher key, and archive", () => {
  const signed = signedManifest(TEST_ARTIFACT);
  assert.doesNotThrow(() =>
    validateCloakBrowserCacheAuthentication(
      {
        schemaVersion: CLOAKBROWSER_CACHE_AUTH_SCHEMA_VERSION,
        signedManifestSha256: sha256(signed.manifest),
        signedManifestBase64: Buffer.from(signed.manifest).toString("base64"),
        signatureBase64: Buffer.from(signed.signature).toString("base64"),
        publisherEd25519PublicKey: signed.publicKey,
        archiveSha256: TEST_ARTIFACT.sha256,
      },
      TEST_ARTIFACT,
      signed.publicKey,
    ),
  );
});

test("rejects forged cache attestation whose manifest digest does not match", () => {
  const signed = signedManifest(TEST_ARTIFACT);
  assert.throws(
    () =>
      validateCloakBrowserCacheAuthentication(
        {
          schemaVersion: CLOAKBROWSER_CACHE_AUTH_SCHEMA_VERSION,
          signedManifestSha256: "1".repeat(64),
          signedManifestBase64: Buffer.from(signed.manifest).toString("base64"),
          signatureBase64: Buffer.from(signed.signature).toString("base64"),
          publisherEd25519PublicKey: signed.publicKey,
          archiveSha256: TEST_ARTIFACT.sha256,
        },
        TEST_ARTIFACT,
        signed.publicKey,
      ),
    /digest does not match its attestation/,
  );
});

test("rejects a cached binary path that traverses outside the locked version directory", async () => {
  const cache = await mkdtemp(join(tmpdir(), "cloak-cache-test-"));
  const versionDir = join(cache, TEST_ARTIFACT.chromiumVersion);
  await mkdir(versionDir);
  await writeFile(join(cache, "outside-browser"), "not trusted");
  try {
    await assert.rejects(
      resolveContainedRegularFile(versionDir, "../outside-browser"),
      /escapes its locked version directory/,
    );
  } finally {
    await rm(cache, { recursive: true, force: true });
  }
});

test("accepts only a regular cached binary inside the locked version directory", async () => {
  const cache = await mkdtemp(join(tmpdir(), "cloak-cache-test-"));
  const versionDir = join(cache, TEST_ARTIFACT.chromiumVersion);
  await mkdir(versionDir);
  await writeFile(join(versionDir, "chrome"), "trusted binary");
  await mkdir(join(versionDir, "directory"));
  try {
    assert.equal(
      await resolveContainedRegularFile(versionDir, "chrome"),
      join(versionDir, "chrome"),
    );
    await assert.rejects(
      resolveContainedRegularFile(versionDir, "directory"),
      /not a regular file/,
    );
  } finally {
    await rm(cache, { recursive: true, force: true });
  }
});

test("rejects a cached binary reached through an intermediate symlink outside the version", async () => {
  const cache = await mkdtemp(join(tmpdir(), "cloak-cache-test-"));
  const versionDir = join(cache, TEST_ARTIFACT.chromiumVersion);
  const outsideDir = join(cache, "outside");
  await mkdir(versionDir);
  await mkdir(outsideDir);
  await writeFile(join(outsideDir, "chrome"), "not trusted");
  await symlink(outsideDir, join(versionDir, "linked"), "dir");
  try {
    await assert.rejects(
      resolveContainedRegularFile(versionDir, "linked/chrome"),
      /resolves outside its locked version directory/,
    );
  } finally {
    await rm(cache, { recursive: true, force: true });
  }
});

function signedManifest(artifact: CloakBrowserPlatformLock): {
  manifest: Uint8Array;
  signature: Uint8Array;
  publicKey: string;
} {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const manifest = Buffer.from(
    `version=${artifact.chromiumVersion}\n${artifact.sha256}  ${artifact.assetFilename}\n`,
  );
  const signature = Buffer.from(sign(null, manifest, privateKey).toString("base64"));
  const jwk = publicKey.export({ format: "jwk" });
  assert.equal(jwk.kty, "OKP");
  assert.ok(jwk.x);
  return {
    manifest,
    signature,
    publicKey: Buffer.from(jwk.x, "base64url").toString("base64"),
  };
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}
