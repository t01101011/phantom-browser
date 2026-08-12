#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  open,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import process from "node:process";
import { BROWSER_PROBE_SOURCE } from "./browser-probe.mjs";
import { buildReport, redact, renderSummary, unknown } from "./evidence.mjs";
import { runNetworkAdapters } from "./network-probes.mjs";

// chrome-remote-interface is owned by the desktop workspace. Resolve it from
// that manifest so this repository-level script works with Yarn workspaces
// without duplicating a root dependency.
const requireDesktop = createRequire(new URL("../../apps/desktop/package.json", import.meta.url));
const CDP = requireDesktop("chrome-remote-interface");

const args = parseArgs(process.argv.slice(2));
if (args.help) {
  process.stdout.write(
    `Usage: node scripts/native-coverage/run.mjs [options]\n\n` +
      `  --engine cft|cloakbrowser   Engine evidence tag (default: cft)\n` +
      `  --binary PATH              Browser executable (CFT cache auto-detected)\n` +
      `  --release-tag TAG          Optional immutable release provenance\n` +
      `  --binary-sha256 HEX        Required expected digest for CloakBrowser\n` +
      `  --output PATH              JSON report path\n` +
      `  --summary PATH             Human summary path\n` +
      `  --timeout-ms N             Bounded launch/probe timeout (default: 20000)\n` +
      `  --network-evidence PATH    Import <=1 MiB parsed packet-observer JSON\n` +
      `  --run-id UUID              Bind imported network evidence to this run\n` +
      `  --capture --interface IF   Advertise approved packet-capture adapter (unparsed evidence stays UNKNOWN)\n`,
  );
  process.exit(0);
}

const allowedArgs = new Set([
  "engine",
  "binary",
  "releaseTag",
  "binarySha256",
  "output",
  "summary",
  "timeoutMs",
  "networkEvidence",
  "runId",
  "capture",
  "interface",
  "help",
]);
for (const key of Object.keys(args)) {
  if (!allowedArgs.has(key)) throw new Error(`Unsupported option: --${key}`);
}

const engine = args.engine ?? "cft";
if (engine !== "cft" && engine !== "cloakbrowser") throw new Error(`Invalid --engine ${engine}`);
const timeoutMs = boundedInteger(args.timeoutMs ?? "20000", 5000, 60000, "--timeout-ms");
const outputPath = resolve(args.output ?? `artifacts/native-coverage/${engine}.json`);
const summaryPath = resolve(args.summary ?? `artifacts/native-coverage/${engine}.txt`);
if (outputPath === summaryPath) throw new Error("--output and --summary must be different paths");
if (engine === "cloakbrowser" && !args.releaseTag)
  throw new Error("--release-tag is required for CloakBrowser evidence");
if (engine === "cloakbrowser" && !/^[0-9a-f]{64}$/i.test(args.binarySha256 ?? ""))
  throw new Error("--binary-sha256 is required for CloakBrowser evidence");
const runId = args.runId ?? randomUUID();
if (args.networkEvidence && !args.runId)
  throw new Error("--run-id is required with --network-evidence to reject stale captures");
if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(runId))
  throw new Error("--run-id must be a UUID");
const binary = resolve(args.binary ?? (await autoDetectCftBinary(engine)));
if (!existsSync(binary)) throw new Error(`Browser binary does not exist: ${binary}`);

const controller = new AbortController();
const report = await withTimeout(
  runBrowserProbe({ engine, binary, args, runId, signal: controller.signal }),
  timeoutMs,
  timeoutMs,
  controller,
);
await mkdir(dirname(outputPath), { recursive: true });
await mkdir(dirname(summaryPath), { recursive: true });
if ((await canonicalDestination(outputPath)) === (await canonicalDestination(summaryPath)))
  throw new Error("--output and --summary resolve to the same destination");
await writePrivateFile(outputPath, `${JSON.stringify(redact(report), null, 2)}\n`);
await writePrivateFile(summaryPath, renderSummary(report));
process.stdout.write(`${renderSummary(report)}JSON: ${outputPath}\nSummary: ${summaryPath}\n`);

async function runBrowserProbe({ engine, binary, args, runId, signal }) {
  const temp = await mkdtemp(join(tmpdir(), "phantom-native-coverage-"));
  let server;
  let child;
  let stderr = "";
  try {
    server = await startProbeServer();
    const preLaunchSha256 = await hashOpenExecutable(binary);
    child = spawn(
      binary,
      [
        "--remote-debugging-port=0",
        `--user-data-dir=${join(temp, "profile")}`,
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--metrics-recording-only",
        `--unsafely-treat-insecure-origin-as-secure=${server.url.slice(0, -1)}`,
        ...(process.getuid?.() === 0 ? ["--no-sandbox"] : []),
        server.url,
      ],
      { detached: process.platform !== "win32", stdio: ["ignore", "ignore", "pipe"] },
    );
    signal.addEventListener("abort", () => void terminate(child), { once: true });
    child.stderr.on("data", (chunk) => {
      stderr = `${stderr}${chunk}`.slice(-4096);
    });
    const port = await waitForDevToolsPort(
      join(temp, "profile", "DevToolsActivePort"),
      10000,
      signal,
    );
    await assertLaunchedExecutable(child, binary);
    const version = await waitForJson(`http://127.0.0.1:${port}/json/version`, 10000, signal);
    const browserVersion = parseBrowserVersion(version.Browser);
    if (!browserVersion) throw new Error("CDP returned no parseable four-part browser version");
    const targets = await waitForTargets(port, 10000, signal);
    const page = targets.find((target) => target.type === "page" && target.url === server.url);
    if (!page) throw new Error("Browser started without a page target");
    const client = await CDP({ target: page.webSocketDebuggerUrl });
    let observations;
    try {
      const evaluated = await client.Runtime.evaluate({
        expression: `(${BROWSER_PROBE_SOURCE})()`,
        awaitPromise: true,
        returnByValue: true,
      });
      if (evaluated.exceptionDetails) throw new Error("Browser probe evaluation failed");
      observations = evaluated.result.value ?? {};
    } finally {
      await client.close();
    }
    observations.proxyRouting = unknown(
      "No controlled egress observer configured; launch proxy fields are not evidence",
    );
    const binarySha256 =
      process.platform === "linux"
        ? await hashOpenExecutable(`/proc/${child.pid}/exe`)
        : await hashOpenExecutable(binary);
    if (binarySha256 !== preLaunchSha256)
      throw new Error("Browser executable changed between provenance check and probe");
    if (args.binarySha256 && binarySha256 !== args.binarySha256.toLowerCase())
      throw new Error("Browser executable does not match --binary-sha256");
    const platformTag = `${process.platform}/${process.arch}`;
    const network = await runNetworkAdapters({
      capture: args.capture,
      interface: args.interface,
      evidencePath: args.networkEvidence,
      provenance: { engine, binarySha256, platform: platformTag, runId },
    });
    return buildReport({
      engine,
      binary: {
        version: browserVersion,
        releaseTag: args.releaseTag,
        sha256: binarySha256,
      },
      platform: { os: process.platform, arch: process.arch, headless: true },
      observations,
      network,
      runId,
    });
  } catch (error) {
    throw new Error(
      `${error instanceof Error ? error.message : String(error)}${stderr ? `; browser stderr: ${sanitize(stderr)}` : ""}`,
    );
  } finally {
    if (child) await terminate(child);
    if (server) await server.close();
    await rm(temp, { recursive: true, force: true });
  }
}

async function autoDetectCftBinary(engine) {
  if (engine !== "cft")
    throw new Error(
      "--binary is required for CloakBrowser; proprietary assets are never downloaded by this harness",
    );
  const roots = [
    join(
      process.env.XDG_CONFIG_HOME ?? join(process.env.HOME ?? "", ".config"),
      "Phantom Browser",
      "chromium",
      "cft",
    ),
  ];
  for (const root of roots) {
    try {
      const manifest = JSON.parse(await readFile(join(root, "current.json"), "utf8"));
      if (
        typeof manifest.version === "string" &&
        /^\d+(?:\.\d+){3}$/.test(manifest.version) &&
        typeof manifest.binaryRelative === "string"
      ) {
        const candidate = resolve(root, manifest.version, manifest.binaryRelative);
        const versionRoot = resolve(root, manifest.version);
        if (candidate.startsWith(`${versionRoot}/`) && existsSync(candidate)) return candidate;
      }
    } catch {
      /* try next supported cache root */
    }
  }
  throw new Error(
    "No cached CFT binary found; pass --binary PATH (the harness does not download browsers)",
  );
}

function parseArgs(values) {
  const result = {};
  const boolean = new Set(["help", "capture"]);
  for (let index = 0; index < values.length; index += 1) {
    const token = values[index];
    if (!token?.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const equalsAt = token.indexOf("=");
    const option = equalsAt === -1 ? token : token.slice(0, equalsAt);
    const inlineValue = equalsAt === -1 ? undefined : token.slice(equalsAt + 1);
    const key = option.slice(2).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if (boolean.has(key)) {
      result[key] = true;
      continue;
    }
    const value = inlineValue ?? values[index + 1];
    if (!value || (inlineValue === undefined && value.startsWith("--")))
      throw new Error(`${option} requires a value`);
    if (inlineValue === undefined) index += 1;
    result[key] = value;
  }
  return result;
}

function boundedInteger(value, min, max, label) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max)
    throw new Error(`${label} must be ${min}..${max}`);
  return parsed;
}

async function startProbeServer() {
  const server = createServer((request, response) => {
    response.writeHead(200, { "content-type": "text/html", "cache-control": "no-store" });
    response.end(
      "<!doctype html><meta charset=utf-8><title>Phantom native coverage probe</title><body></body>",
    );
  });
  await new Promise((resolvePromise, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolvePromise);
  });
  const address = server.address();
  return {
    url: `http://127.0.0.1:${address.port}/`,
    close: () => new Promise((resolvePromise) => server.close(resolvePromise)),
  };
}

async function waitForDevToolsPort(path, timeoutMs, signal) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (signal.aborted) throw new Error("Harness aborted");
    try {
      const [line] = (await readFile(path, "utf8")).split(/\r?\n/);
      const port = Number(line);
      if (Number.isInteger(port) && port > 0 && port <= 65535) return port;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 50));
  }
  throw new Error("Timed out waiting for Chromium DevToolsActivePort");
}

async function assertLaunchedExecutable(child, expectedPath) {
  if (process.platform !== "linux") return;
  const [actual, expected] = await Promise.all([
    realpath(`/proc/${child.pid}/exe`),
    realpath(expectedPath),
  ]);
  if (actual !== expected)
    throw new Error("Launched process executable does not match hashed binary");
}

async function waitForJson(url, timeoutMs, signal) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    if (signal.aborted) throw new Error("Harness aborted");
    try {
      const response = await fetch(url, { signal });
      if (response.ok) return await response.json();
    } catch (error) {
      last = error;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error(`Timed out waiting for ${url}: ${String(last ?? "no response")}`);
}

async function waitForTargets(port, timeoutMs, signal) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const targets = await waitForJson(
      `http://127.0.0.1:${port}/json/list`,
      Math.min(1000, timeoutMs),
      signal,
    );
    if (Array.isArray(targets) && targets.some((target) => target.type === "page")) return targets;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
  throw new Error("Timed out waiting for a page target");
}

async function hashOpenExecutable(path) {
  const resolvedPath = await realpath(path);
  const handle = await open(resolvedPath, "r");
  const hash = createHash("sha256");
  try {
    await new Promise((resolvePromise, reject) => {
      const stream = handle.createReadStream({ autoClose: false });
      stream.on("data", (chunk) => hash.update(chunk));
      stream.on("error", reject);
      stream.on("end", resolvePromise);
    });
    if ((await realpath(path)) !== resolvedPath)
      throw new Error("Browser executable changed during probe");
    return hash.digest("hex");
  } finally {
    await handle.close();
  }
}

function parseBrowserVersion(browser) {
  return typeof browser === "string" ? (browser.match(/(\d+(?:\.\d+){3,4})/)?.[1] ?? null) : null;
}
function sanitize(value) {
  return value
    .replace(/(?:https?:\/\/)?[^\s:@]+:[^\s@]+@[^\s]+/g, "[REDACTED_URL]")
    .replace(/[\r\n]+/g, " ")
    .slice(-1000);
}
async function terminate(child) {
  if (child.exitCode !== null) return;
  signalTree(child, "SIGTERM");
  await Promise.race([
    new Promise((resolvePromise) => child.once("exit", resolvePromise)),
    new Promise((resolvePromise) => setTimeout(resolvePromise, 1500)),
  ]);
  if (child.exitCode === null) {
    signalTree(child, "SIGKILL");
    await Promise.race([
      new Promise((resolvePromise) => child.once("exit", resolvePromise)),
      new Promise((resolvePromise) => setTimeout(resolvePromise, 1500)),
    ]);
  }
}
function signalTree(child, signal) {
  if (process.platform !== "win32") {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch {
      // fall back to the direct child
    }
  }
  child.kill(signal);
}
async function withTimeout(promise, timeoutMs, label, controller) {
  let timer;
  let timeoutError;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          timeoutError = new Error(`Harness exceeded ${label}ms`);
          reject(timeoutError);
        }, timeoutMs);
      }),
    ]);
  } catch (error) {
    if (error === timeoutError) {
      await Promise.race([
        promise.catch(() => undefined),
        new Promise((resolvePromise) => setTimeout(resolvePromise, 5000)),
      ]);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function writePrivateFile(path, content) {
  try {
    const current = await lstat(path);
    if (!current.isFile() || current.isSymbolicLink())
      throw new Error(`Refusing unsafe output path: ${path}`);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const temporary = `${path}.tmp-${process.pid}-${Date.now()}`;
  try {
    await writeFile(temporary, content, { mode: 0o600, flag: "wx" });
    await chmod(temporary, 0o600);
    await rename(temporary, path);
  } finally {
    await rm(temporary, { force: true });
  }
}

async function canonicalDestination(path) {
  return join(await realpath(dirname(path)), basename(path));
}
