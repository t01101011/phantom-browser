import { createPublicKey, verify as cryptoVerify } from "node:crypto";
import lockJson from "./cloakbrowser-engine-lock.json" with { type: "json" };

export interface CloakBrowserPlatformLock {
  releaseTag: string;
  chromiumVersion: string;
  assetFilename: string;
  sha256: string;
  channel: string;
  license: string;
}

export interface CloakBrowserEngineLock {
  schemaVersion: number;
  engine: "cloakbrowser";
  upstreamRepository: string;
  upstreamWrapperRevision: string;
  publisherEd25519PublicKey: string;
  trustRootProvenance: string;
  platforms: Record<string, CloakBrowserPlatformLock>;
}

export const CLOAKBROWSER_ENGINE_LOCK = lockJson as CloakBrowserEngineLock;

export function cloakBrowserPlatformKey(
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch,
): string {
  if (platform === "darwin" && (arch === "x64" || arch === "arm64")) {
    return `darwin-${arch}`;
  }
  if (platform === "linux" && (arch === "x64" || arch === "arm64")) {
    return `linux-${arch}`;
  }
  if (platform === "win32" && arch === "x64") return "win32-x64";
  return `${platform}-${arch}`;
}

export function resolveLockedCloakBrowserArtifact(
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch,
  lock: CloakBrowserEngineLock = CLOAKBROWSER_ENGINE_LOCK,
): CloakBrowserPlatformLock {
  const platformKey = cloakBrowserPlatformKey(platform, arch);
  const artifact = lock.platforms[platformKey];
  if (!artifact) {
    throw new Error(
      `Locked CloakBrowser release ${lock.upstreamWrapperRevision} has no artifact for ${platformKey}; refusing to select another release`,
    );
  }
  validateArtifactLock(platformKey, artifact);
  return artifact;
}

export function verifySignedCloakBrowserManifest(
  manifestBytes: Uint8Array,
  signatureBytes: Uint8Array,
  artifact: CloakBrowserPlatformLock,
  publicKeyBase64: string = CLOAKBROWSER_ENGINE_LOCK.publisherEd25519PublicKey,
): void {
  const signatureText = Buffer.from(signatureBytes).toString("utf8").trim();
  const signature = Buffer.from(signatureText, "base64");
  if (signature.length !== 64 || signature.toString("base64") !== signatureText) {
    throw new Error("Malformed CloakBrowser SHA256SUMS.sig");
  }

  const rawPublicKey = Buffer.from(publicKeyBase64, "base64");
  if (rawPublicKey.length !== 32 || rawPublicKey.toString("base64") !== publicKeyBase64) {
    throw new Error("Pinned CloakBrowser Ed25519 public key is malformed");
  }

  const publicKey = createPublicKey({
    key: {
      kty: "OKP",
      crv: "Ed25519",
      x: rawPublicKey.toString("base64url"),
    },
    format: "jwk",
  });
  if (!cryptoVerify(null, manifestBytes, publicKey, signature)) {
    throw new Error("CloakBrowser SHA256SUMS signature verification failed");
  }

  const manifest = Buffer.from(manifestBytes).toString("utf8");
  const version = parseManifestVersion(manifest);
  if (version !== artifact.chromiumVersion) {
    throw new Error(
      `Signed CloakBrowser manifest version ${version ?? "missing"} does not match locked version ${artifact.chromiumVersion}`,
    );
  }
  const signedHash = parseManifestChecksum(manifest, artifact.assetFilename);
  if (signedHash !== artifact.sha256) {
    throw new Error(
      `Signed CloakBrowser checksum for ${artifact.assetFilename} does not match the engine lock`,
    );
  }
}

function validateArtifactLock(platformKey: string, artifact: CloakBrowserPlatformLock): void {
  if (!/^chromium-v\d+(?:\.\d+){3,4}(?:-pro)?$/.test(artifact.releaseTag)) {
    throw new Error(`Invalid CloakBrowser release tag locked for ${platformKey}`);
  }
  if (!/^\d+(?:\.\d+){3,4}$/.test(artifact.chromiumVersion)) {
    throw new Error(`Invalid CloakBrowser Chromium version locked for ${platformKey}`);
  }
  if (!/^[a-f0-9]{64}$/.test(artifact.sha256)) {
    throw new Error(`Invalid CloakBrowser SHA-256 locked for ${platformKey}`);
  }
  if (!artifact.assetFilename || artifact.assetFilename.includes("/")) {
    throw new Error(`Invalid CloakBrowser asset filename locked for ${platformKey}`);
  }
}

function parseManifestVersion(manifest: string): string | null {
  const line = manifest.split(/\r?\n/).find((candidate) => candidate.startsWith("version="));
  return line?.slice("version=".length).trim() || null;
}

function parseManifestChecksum(manifest: string, assetFilename: string): string | null {
  for (const line of manifest.split(/\r?\n/)) {
    const match = /^([a-f0-9]{64})\s+\*?(.+)$/i.exec(line.trim());
    if (match?.[2] === assetFilename) return match[1]!.toLowerCase();
  }
  return null;
}
