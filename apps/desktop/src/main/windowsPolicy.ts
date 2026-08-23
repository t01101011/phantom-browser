import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileP = promisify(execFile);

export const WEBRTC_POLICY_NAME = "WebRtcIPHandling";
export const WEBRTC_POLICY_VALUE = "disable_non_proxied_udp";
// Chrome for Testing's Windows policy provider reads the machine policy
// location. HKCU is accepted by reg.exe but is not consumed by CFT, which
// made the previous "successful" per-user write a false positive.
export const CFT_WINDOWS_POLICY_KEY = "HKLM\\SOFTWARE\\Policies\\Google\\Chrome for Testing";

export interface RegCommand {
  file: string;
  args: string[];
}

export interface ElevatedRegCommand extends RegCommand {
  script: string;
}

/** Resolve reg.exe without relying on Electron's potentially minimal PATH. */
export function windowsRegExe(env: NodeJS.ProcessEnv = process.env): string {
  const systemRoot = env.SystemRoot ?? env.SYSTEMROOT;
  return systemRoot ? `${systemRoot}\\System32\\reg.exe` : "reg.exe";
}

export function buildWebRtcPolicyAddCommand(env: NodeJS.ProcessEnv = process.env): RegCommand {
  return {
    file: windowsRegExe(env),
    args: [
      "ADD",
      CFT_WINDOWS_POLICY_KEY,
      "/v",
      WEBRTC_POLICY_NAME,
      "/t",
      "REG_SZ",
      "/d",
      WEBRTC_POLICY_VALUE,
      "/f",
      "/reg:64",
    ],
  };
}

export function buildWebRtcPolicyQueryCommand(env: NodeJS.ProcessEnv = process.env): RegCommand {
  return {
    file: windowsRegExe(env),
    args: ["QUERY", CFT_WINDOWS_POLICY_KEY, "/v", WEBRTC_POLICY_NAME, "/reg:64"],
  };
}

function powershellExe(env: NodeJS.ProcessEnv = process.env): string {
  const systemRoot = env.SystemRoot ?? env.SYSTEMROOT;
  return systemRoot
    ? `${systemRoot}\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
    : "powershell.exe";
}

function quotePowerShellLiteral(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

/** Build a command that triggers the normal Windows UAC consent dialog. */
export function buildElevatedWebRtcPolicyInstallCommand(
  env: NodeJS.ProcessEnv = process.env,
): ElevatedRegCommand {
  const add = buildWebRtcPolicyAddCommand(env);
  // Start-Process flattens ArgumentList into a single command line. Preserve
  // arguments containing spaces by embedding Windows command-line quotes.
  const argumentList = add.args
    .map((arg) => (arg.includes(" ") ? `\"${arg.replaceAll('"', '\\"')}\"` : arg))
    .map(quotePowerShellLiteral)
    .join(", ");
  const script =
    `try { $process = Start-Process -FilePath ${quotePowerShellLiteral(add.file)} ` +
    `-ArgumentList @(${argumentList}) -Verb RunAs -Wait -PassThru -ErrorAction Stop; ` +
    `if ($null -eq $process) { exit 1 }; exit $process.ExitCode } catch { exit 1 }`;
  return {
    file: powershellExe(env),
    args: ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
    script,
  };
}

export function registryContainsWebRtcPolicy(stdout: string): boolean {
  return new RegExp(
    `^\\s*${WEBRTC_POLICY_NAME}\\s+REG_SZ\\s+${WEBRTC_POLICY_VALUE}\\s*$`,
    "im",
  ).test(stdout);
}

export async function installAndVerifyWindowsWebRtcPolicy(): Promise<void> {
  const query = buildWebRtcPolicyQueryCommand();
  let installed = false;
  try {
    const { stdout } = await execFileP(query.file, query.args, { windowsHide: true });
    installed = registryContainsWebRtcPolicy(stdout);
  } catch {
    // Missing key/value is expected on first launch; install it below.
  }

  if (!installed) {
    const elevated = buildElevatedWebRtcPolicyInstallCommand();
    try {
      await execFileP(elevated.file, elevated.args, { windowsHide: true });
    } catch (cause) {
      throw new Error(
        "Chrome for Testing WebRTC policy requires one-time administrator approval. " +
          "Approve the Windows UAC prompt or ask an administrator to install the policy, then retry.",
        { cause },
      );
    }
  }

  const { stdout } = await execFileP(query.file, query.args, { windowsHide: true });
  if (!registryContainsWebRtcPolicy(stdout)) {
    throw new Error(`registry policy value did not verify at ${CFT_WINDOWS_POLICY_KEY}`);
  }
}
