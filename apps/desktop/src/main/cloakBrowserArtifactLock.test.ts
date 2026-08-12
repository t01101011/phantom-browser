import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import test from "node:test";
import {
  CLOAKBROWSER_ENGINE_LOCK,
  resolveLockedCloakBrowserArtifact,
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
