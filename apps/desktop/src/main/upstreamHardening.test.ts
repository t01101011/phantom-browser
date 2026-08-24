import assert from "node:assert/strict";
import test from "node:test";
import {
  buildChromiumChildEnv,
  createWarningThrottle,
  sendToRendererSafely,
  shouldRunBootstrapDiagnostics,
  versionsEligibleForGc,
} from "./upstreamHardening.ts";

test("engine GC retains both newly installed and previously active versions", () => {
  assert.deepEqual(
    versionsEligibleForGc(
      ["146.0.1.1", "147.0.2.2", "148.0.3.3", "scratch", "148.0.3.3.partial"],
      "148.0.3.3",
      "147.0.2.2",
    ),
    ["146.0.1.1"],
  );
});

test("Linux Chromium child inherits desktop session without Electron contamination", () => {
  const env = buildChromiumChildEnv(
    {
      PATH: "/bin",
      HOME: "/home/tk",
      DISPLAY: ":1",
      WAYLAND_DISPLAY: "wayland-0",
      XAUTHORITY: "/tmp/auth",
      XDG_RUNTIME_DIR: "/run/user/1000",
      DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/dbus",
      ELECTRON_RUN_AS_NODE: "1",
      CHROME_DESKTOP: "bad",
    },
    "linux",
  );
  assert.equal(env.DISPLAY, ":1");
  assert.equal(env.WAYLAND_DISPLAY, "wayland-0");
  assert.equal(env.XAUTHORITY, "/tmp/auth");
  assert.equal(env.XDG_RUNTIME_DIR, "/run/user/1000");
  assert.equal(env.DBUS_SESSION_BUS_ADDRESS, "unix:path=/run/dbus");
  assert.equal(env.ELECTRON_RUN_AS_NODE, undefined);
  assert.equal(env.CHROME_DESKTOP, undefined);
});

test("renderer IPC drops sends after webContents is destroyed", () => {
  let sends = 0;
  const destroyed = {
    webContents: {
      isDestroyed: () => true,
      send: () => {
        sends += 1;
      },
    },
  };
  assert.equal(sendToRendererSafely(destroyed, "status", { ok: true }), false);
  assert.equal(sends, 0);
});

test("renderer IPC treats a teardown race during send as a dropped event", () => {
  const racing = {
    webContents: {
      isDestroyed: () => false,
      send: () => {
        throw new Error("Object has been destroyed");
      },
    },
  };
  assert.equal(sendToRendererSafely(racing, "status"), false);
});

test("duplicate bridge warnings are throttled while distinct failures remain visible", () => {
  let now = 100_000;
  const emitted: string[] = [];
  const warn = createWarningThrottle(
    30_000,
    () => now,
    (message) => emitted.push(message),
  );
  warn("proxy refused");
  warn("proxy refused");
  warn("auth failed");
  now += 30_000;
  warn("proxy refused");
  assert.deepEqual(emitted, ["proxy refused", "auth failed", "proxy refused"]);
});

test("bootstrap diagnostics are opt-in", () => {
  assert.equal(shouldRunBootstrapDiagnostics({}), false);
  assert.equal(shouldRunBootstrapDiagnostics({ PHANTOM_DEBUG: "1" }), true);
  assert.equal(shouldRunBootstrapDiagnostics({ PHANTOM_DEBUG: "0" }), false);
});
