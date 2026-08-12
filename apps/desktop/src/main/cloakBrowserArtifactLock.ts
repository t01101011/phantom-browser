import { createHash, createPublicKey, verify as cryptoVerify } from "node:crypto";
import { lstat, realpath } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
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
export const CLOAKBROWSER_CACHE_AUTH_SCHEMA_VERSION = 1;

export interface CloakBrowserCacheAuthentication {
  schemaVersion: number;
  signedManifestSha256: string;
  signedManifestBase64: string;
  signatureBase64: string;
  publisherEd25519PublicKey: string;
  archiveSha256: string;
}

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

export function validateCloakBrowserCacheAuthentication(
  authentication: CloakBrowserCacheAuthentication | undefined,
  artifact: CloakBrowserPlatformLock,
  publisherEd25519PublicKey: string = CLOAKBROWSER_ENGINE_LOCK.publisherEd25519PublicKey,
): void {
  if (authentication?.schemaVersion !== CLOAKBROWSER_CACHE_AUTH_SCHEMA_VERSION) {
    throw new Error("CloakBrowser cache lacks authenticated-manifest attestation");
  }
  if (!/^[a-f0-9]{64}$/.test(authentication.signedManifestSha256)) {
    throw new Error("CloakBrowser cache has an invalid signed-manifest digest");
  }
  if (authentication.publisherEd25519PublicKey !== publisherEd25519PublicKey) {
    throw new Error("CloakBrowser cache was authenticated by an untrusted publisher key");
  }
  if (authentication.archiveSha256 !== artifact.sha256) {
    throw new Error("CloakBrowser cache archive digest does not match the engine lock");
  }
  const manifestBytes = decodeCanonicalBase64(
    authentication.signedManifestBase64,
    "signed manifest",
  );
  const signatureBytes = decodeCanonicalBase64(authentication.signatureBase64, "signature");
  const digest = createHash("sha256").update(manifestBytes).digest("hex");
  if (digest !== authentication.signedManifestSha256) {
    throw new Error("CloakBrowser cache signed-manifest digest does not match its attestation");
  }
  verifySignedCloakBrowserManifest(
    manifestBytes,
    signatureBytes,
    artifact,
    publisherEd25519PublicKey,
  );
}

function decodeCanonicalBase64(value: string, label: string): Buffer {
  const decoded = Buffer.from(value, "base64");
  if (!value || decoded.toString("base64") !== value) {
    throw new Error(`CloakBrowser cache has malformed ${label} bytes`);
  }
  return decoded;
}

export async function resolveContainedRegularFile(
  rootDir: string,
  binaryRelative: string,
): Promise<string> {
  if (!binaryRelative || isAbsolute(binaryRelative)) {
    throw new Error("Cached browser binary path must be relative");
  }
  const root = resolve(rootDir);
  const candidate = resolve(root, binaryRelative);
  const fromRoot = relative(root, candidate);
  if (!fromRoot || fromRoot.startsWith("..") || isAbsolute(fromRoot)) {
    throw new Error("Cached browser binary path escapes its locked version directory");
  }
  const info = await lstat(candidate);
  if (!info.isFile()) {
    throw new Error("Cached browser binary path is not a regular file");
  }
  const [realRoot, realCandidate] = await Promise.all([realpath(root), realpath(candidate)]);
  const realFromRoot = relative(realRoot, realCandidate);
  if (!realFromRoot || realFromRoot.startsWith("..") || isAbsolute(realFromRoot)) {
    throw new Error("Cached browser binary resolves outside its locked version directory");
  }
  return realCandidate;
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
