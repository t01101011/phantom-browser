import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { build } from "esbuild";
// Node's strip-types runner resolves the production CDP source directly.
import { CdpSession } from "../../../../packages/cdp-driver/src/CdpSession.ts";

const bundleDir = await mkdtemp(join(tmpdir(), "phantom-launch-test-bundle-"));
const bundlePath = join(bundleDir, "ChromiumBrowserDriver.cjs");
const electronStubPath = join(bundleDir, "electron-stub.cjs");
const profileManagerStubPath = join(bundleDir, "profile-manager-stub.cjs");
const cdpDriverStubPath = join(bundleDir, "cdp-driver-stub.cjs");
const bridgeStubPath = join(bundleDir, "bridge-stub.cjs");
const proxyGeoStubPath = join(bundleDir, "proxy-geo-stub.cjs");
const companionStubPath = join(bundleDir, "companion-stub.cjs");
await Promise.all([
  writeFile(electronStubPath, 'exports.app = { getPath: () => "/tmp" };\n', "utf8"),
  writeFile(
    profileManagerStubPath,
    "exports.reconcileDeviceFamilyToHost = (fingerprint) => fingerprint;\n",
    "utf8",
  ),
  writeFile(cdpDriverStubPath, "exports.CdpSession = class CdpSession {};\n", "utf8"),
  writeFile(
    bridgeStubPath,
    "exports.startBridgeForProfile = async () => ''; exports.stopBridgeForProfile = async () => {};\n",
    "utf8",
  ),
  writeFile(proxyGeoStubPath, "exports.probeProxyGeo = async () => ({});\n", "utf8"),
  writeFile(companionStubPath, "exports.companionDir = () => '/tmp/companion';\n", "utf8"),
]);
await build({
  entryPoints: [new URL("./ChromiumBrowserDriver.ts", import.meta.url).pathname],
  outfile: bundlePath,
  bundle: true,
  format: "cjs",
  platform: "node",
  alias: {
    electron: electronStubPath,
    "@multizen/profile-manager": profileManagerStubPath,
    "@multizen/cdp-driver": cdpDriverStubPath,
  },
  plugins: [
    {
      name: "launch-test-stubs",
      setup(api) {
        api.onResolve({ filter: /^\.\/socks5Bridge$/ }, () => ({ path: bridgeStubPath }));
        api.onResolve({ filter: /^\.\/proxyGeo$/ }, () => ({ path: proxyGeoStubPath }));
        api.onResolve({ filter: /^\.\/extensions\/companion$/ }, () => ({
          path: companionStubPath,
        }));
      },
    },
  ],
  logLevel: "silent",
});
const { ChromiumBrowserDriver } = await import(pathToFileURL(bundlePath).href);

test.after(async () => rm(bundleDir, { recursive: true, force: true }));

const proxy = { type: "http", host: "127.0.0.1", port: 8080 } as const;
const fingerprint = {
  device: "linux-desktop-intel",
  userAgent: "Mozilla/5.0 Chrome/147.0.0.0",
  platform: "Linux x86_64",
  clientHints: {
    secChUa: '"Chromium";v="147"',
    secChUaPlatform: "Linux",
    secChUaPlatformVersion: "6.8.0",
    secChUaArch: "x86",
    secChUaBitness: "64",
    secChUaMobile: "?0",
    secChUaModel: "",
    secChUaFullVersionList: '"Chromium";v="147.0.0.0"',
  },
  locale: "en-US",
  languages: ["en-US", "en"],
  acceptLanguage: "en-US,en;q=0.9",
  timezone: "UTC",
  country: "zz",
  screen: { width: 1280, height: 800 },
  dpr: 1,
  webgl: { vendor: "Intel", renderer: "Intel" },
  hardwareConcurrency: 4,
  deviceMemory: 8,
};

class FakeChild extends EventEmitter {
  pid = 4242;
  stderr = new EventEmitter();
  killed = false;
  kill(): boolean {
    this.killed = true;
    return true;
  }
}

async function harness(options: {
  engine?: "cft" | "cloakbrowser";
  coordinates?: boolean;
  readinessError?: Error;
  bootstrapError?: Error;
  geolocationError?: Error;
  futureProtectionFailure?: boolean;
  futurePageMissingContext?: boolean;
}) {
  const root = await mkdtemp(join(tmpdir(), "phantom-launch-boundary-"));
  const calls: string[] = [];
  const child = new FakeChild();
  let protectionFailureCallback: ((error: unknown) => Promise<void> | void) | undefined;
  let emitAttached:
    | ((params: { sessionId: string; targetInfo: { targetId: string; type: string } }) => void)
    | undefined;
  let session: {
    closeBrowser: () => Promise<void>;
    close: () => Promise<void>;
    bootstrapTargets: (
      configure: (send: (method: string) => Promise<unknown>, ctx: object) => Promise<void>,
    ) => Promise<void>;
    watchUrlForBinding: () => Promise<void>;
  } = {
    closeBrowser: async () => {
      calls.push("close-browser");
      child.kill();
    },
    close: async () => {
      calls.push("close-session");
    },
    bootstrapTargets: async (
      configure: (send: (method: string) => Promise<unknown>, ctx: object) => Promise<void>,
    ) => {
      calls.push("bootstrap");
      if (options.bootstrapError) throw options.bootstrapError;
      await configure(
        async (method: string) => {
          if (method === "Emulation.setGeolocationOverride" && options.geolocationError) {
            throw options.geolocationError;
          }
          return {};
        },
        { targetId: "page-1", type: "page", isRoot: true },
      );
    },
    watchUrlForBinding: async () => {},
  };
  const profileId = "launch-boundary";
  const profile = {
    id: profileId,
    name: "Launch boundary",
    tags: [],
    proxy,
    fingerprint,
    dataDir: root,
    createdAt: new Date(0).toISOString(),
    updatedAt: new Date(0).toISOString(),
  };
  const profileManager = {
    get: () => profile,
    markOpened: () => {},
    update: () => {},
    setProxyCountry: () => {},
  };
  const dependencies = {
    probeProxyGeo: async () => ({
      country: "ZZ",
      countryName: "United States",
      timezone: "UTC",
      city: "Test",
      ip: "8.8.8.8",
      ...(options.coordinates === false ? {} : { latitude: 1, longitude: 2 }),
    }),
    startBridgeForProfile: async () => {
      calls.push("start-bridge");
      return "socks5://127.0.0.1:9999";
    },
    stopBridgeForProfile: async () => {
      calls.push("stop-bridge");
    },
    ensureWebRtcPolicy: async () => {},
    spawn: () => {
      calls.push("spawn");
      return child;
    },
    createSession: (sessionOptions: ConstructorParameters<typeof CdpSession>[0]) => {
      protectionFailureCallback = sessionOptions.onProtectionFailure;
      if (options.futurePageMissingContext) {
        const realSession = new CdpSession(sessionOptions);
        const client = {
          Target: {
            setAutoAttach: async () => {},
            getTargets: async () => ({ targetInfos: [] }),
            attachToTarget: async () => ({ sessionId: "existing-session" }),
          },
          on: (
            event: string,
            callback: (params: {
              sessionId: string;
              targetInfo: { targetId: string; type: string };
            }) => void,
          ) => {
            if (event === "Target.attachedToTarget") emitAttached = callback;
          },
          send: async (method: string, _params?: unknown, sessionId?: string) => {
            calls.push(method);
            if (method === "Runtime.evaluate" && sessionId === "future-session") {
              throw new Error("Cannot find default execution context");
            }
            return {};
          },
          close: async () => {
            calls.push("close-session");
          },
        };
        (realSession as unknown as { client: unknown }).client = client;
        realSession.closeBrowser = async () => {
          calls.push("close-browser");
          child.kill();
        };
        session = realSession as unknown as typeof session;
      }
      return session;
    },
    waitForCdpSessionReady: async () => {
      calls.push("readiness");
      if (options.readinessError) throw options.readinessError;
    },
    killBrowsersUsingDataDir: async () => {
      calls.push("kill-data-dir");
    },
    isPidAlive: () => !child.killed,
    createWindowWatcher: () => setInterval(() => {}, 60_000),
    gracefulShutdown: async () => {
      calls.push("close-browser");
      child.kill();
      await session.close();
    },
  };
  const driver = new ChromiumBrowserDriver({
    profileManager,
    chromiumBootstrap: {
      resolveBinaryPath: () => "/test/chromium",
      getEngine: () => options.engine ?? "cft",
      getStatus: () => ({ kind: "ready", version: "147.0.0.0" }),
    },
    extensionStoreRoot: join(root, "extensions"),
    getSettings: () => ({ proxyProbeTimeoutMs: 10, cdpReadyTimeoutMs: 10 }),
    launchDependencies: dependencies,
  });
  const triggerFutureProtectionFailure = async () => {
    assert(options.futureProtectionFailure);
    assert(protectionFailureCallback);
    await protectionFailureCallback(new Error("future target geolocation rejected"));
  };
  const triggerFuturePageMissingContext = async () => {
    assert(options.futurePageMissingContext);
    assert(emitAttached);
    emitAttached({
      sessionId: "future-session",
      targetInfo: { targetId: "future-page", type: "page" },
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
  };
  return {
    calls,
    child,
    driver,
    profileId,
    root,
    triggerFutureProtectionFailure,
    triggerFuturePageMissingContext,
  };
}

async function expectPrimaryCause(promise: Promise<unknown>, primary: Error): Promise<void> {
  await assert.rejects(promise, (error: unknown) => {
    assert(error instanceof Error);
    assert.equal(error.message, "Browser launch protection failed; launch aborted");
    assert.equal(error.cause, primary);
    return true;
  });
}

test("real launch blocks missing proxy coordinates before spawn even when degraded coherence is accepted", async () => {
  const h = await harness({ coordinates: false });
  try {
    await assert.rejects(
      h.driver.launch(h.profileId, { acceptDegradedCoherence: true }),
      /Geolocation protection unavailable; launch blocked/,
    );
    assert.equal(h.calls.includes("spawn"), false);
    assert.equal(h.calls.includes("start-bridge"), false);
  } finally {
    await rm(h.root, { recursive: true, force: true });
  }
});

test("real launch readiness rejection cleans child, partial session, data-dir processes and bridge while preserving cause", async () => {
  const primary = new Error("readiness rejected");
  const h = await harness({ readinessError: primary });
  try {
    await expectPrimaryCause(h.driver.launch(h.profileId), primary);
    assert.equal(h.child.killed, true);
    assert.deepEqual(h.calls, [
      "start-bridge",
      "spawn",
      "readiness",
      "close-session",
      "kill-data-dir",
      "stop-bridge",
    ]);
  } finally {
    await rm(h.root, { recursive: true, force: true });
  }
});

test("real launch bootstrap rejection cleans all acquired launch resources while preserving cause", async () => {
  const primary = new Error("bootstrap rejected");
  const h = await harness({ bootstrapError: primary });
  try {
    await expectPrimaryCause(h.driver.launch(h.profileId), primary);
    assert.equal(h.child.killed, true);
    assert.deepEqual(h.calls, [
      "start-bridge",
      "spawn",
      "readiness",
      "bootstrap",
      "close-session",
      "kill-data-dir",
      "stop-bridge",
    ]);
  } finally {
    await rm(h.root, { recursive: true, force: true });
  }
});

for (const engine of ["cft", "cloakbrowser"] as const) {
  test(`real launch aborts ${engine} when required CDP geolocation is rejected`, async () => {
    const primary = new Error(`${engine} CDP rejected geolocation`);
    const h = await harness({ engine, geolocationError: primary });
    try {
      await assert.rejects(h.driver.launch(h.profileId), (error: unknown) => {
        assert(error instanceof Error);
        assert.equal(error.message, "Browser launch protection failed; launch aborted");
        assert(error.cause instanceof Error);
        assert.match(
          error.cause.message,
          new RegExp(`${engine} geolocation protection failed closed`),
        );
        assert.equal(error.cause.cause, primary);
        return true;
      });
      assert.equal(h.child.killed, true);
      assert.deepEqual(h.calls.slice(-3), ["close-session", "kill-data-dir", "stop-bridge"]);
    } finally {
      await rm(h.root, { recursive: true, force: true });
    }
  });
}

test("future-target protection failure after ownership transfer closes tracked browser and bridge", async () => {
  const h = await harness({ futureProtectionFailure: true });
  try {
    const launched = await h.driver.launch(h.profileId);
    assert.equal(launched.id, h.profileId);

    await h.triggerFutureProtectionFailure();

    assert.equal(h.child.killed, true);
    assert.equal(h.driver.isRunning(h.profileId), false);
    assert.ok(h.calls.includes("close-browser"));
    assert.deepEqual(h.calls.slice(-3), ["close-session", "kill-data-dir", "stop-bridge"]);
  } finally {
    await rm(h.root, { recursive: true, force: true });
  }
});

test("future paused page without a default execution context stays open after its preload is installed", async () => {
  const h = await harness({ futurePageMissingContext: true });
  try {
    await h.driver.launch(h.profileId);
    await h.triggerFuturePageMissingContext();

    assert.equal(h.driver.isRunning(h.profileId), true);
    assert.equal(h.child.killed, false);
    assert.equal(h.calls.includes("stop-bridge"), false);
  } finally {
    await h.driver.close(h.profileId);
    await rm(h.root, { recursive: true, force: true });
  }
});
