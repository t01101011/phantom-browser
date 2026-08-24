const LINUX_DESKTOP_ENV_KEYS = [
  "DISPLAY",
  "WAYLAND_DISPLAY",
  "XAUTHORITY",
  "XDG_RUNTIME_DIR",
  "XDG_SESSION_TYPE",
  "XDG_CURRENT_DESKTOP",
  "DESKTOP_SESSION",
  "DBUS_SESSION_BUS_ADDRESS",
] as const;

export function buildChromiumChildEnv(
  source: NodeJS.ProcessEnv,
  platform: NodeJS.Platform,
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    PATH: source.PATH ?? "/usr/bin:/bin:/usr/sbin:/sbin",
    HOME: source.HOME ?? "",
    USER: source.USER ?? "",
    LOGNAME: source.LOGNAME ?? source.USER ?? "",
    SHELL: source.SHELL ?? "/bin/sh",
    LANG: source.LANG ?? "en_US.UTF-8",
    LC_ALL: source.LC_ALL ?? "",
    TMPDIR: source.TMPDIR ?? "/tmp",
    DYLD_FALLBACK_FRAMEWORK_PATH: source.DYLD_FALLBACK_FRAMEWORK_PATH ?? "",
  };
  if (platform === "linux") {
    for (const key of LINUX_DESKTOP_ENV_KEYS) {
      if (source[key] !== undefined) env[key] = source[key];
    }
  }
  return env;
}

export function versionsEligibleForGc(
  entries: readonly string[],
  keep: string,
  alsoKeep?: string | null,
): string[] {
  return entries.filter(
    (entry) => entry !== keep && entry !== alsoKeep && /^\d+(?:\.\d+){3,4}$/.test(entry),
  );
}

interface RendererWindowLike {
  webContents: {
    isDestroyed(): boolean;
    send(channel: string, ...args: unknown[]): void;
  };
}

export function sendToRendererSafely(
  window: RendererWindowLike | null | undefined,
  channel: string,
  ...args: unknown[]
): boolean {
  if (!window || window.webContents.isDestroyed()) return false;
  try {
    window.webContents.send(channel, ...args);
    return true;
  } catch (error) {
    if (/destroyed|disposed/i.test((error as Error).message)) return false;
    throw error;
  }
}

export function createWarningThrottle(
  intervalMs: number,
  now: () => number,
  emit: (message: string) => void,
): (message: string) => void {
  const lastEmittedAt = new Map<string, number>();
  return (message) => {
    const current = now();
    const previous = lastEmittedAt.get(message);
    if (previous !== undefined && current - previous < intervalMs) return;
    lastEmittedAt.set(message, current);
    emit(message);
  };
}

export function shouldRunBootstrapDiagnostics(env: NodeJS.ProcessEnv): boolean {
  return env.PHANTOM_DEBUG === "1";
}
