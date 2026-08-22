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

export function registryContainsWebRtcPolicy(stdout: string): boolean {
  return new RegExp(`${WEBRTC_POLICY_NAME}\\s+REG_SZ\\s+${WEBRTC_POLICY_VALUE}`, "i").test(stdout);
}

export async function installAndVerifyWindowsWebRtcPolicy(): Promise<void> {
  const add = buildWebRtcPolicyAddCommand();
  const query = buildWebRtcPolicyQueryCommand();
  try {
    await execFileP(add.file, add.args, { windowsHide: true });
  } catch (cause) {
    throw new Error(
      "Chrome for Testing WebRTC policy requires one-time administrator approval. " +
        "Run Phantom elevated or ask an administrator to install the policy, then retry.",
      { cause },
    );
  }
  const { stdout } = await execFileP(query.file, query.args, { windowsHide: true });
  if (!registryContainsWebRtcPolicy(stdout)) {
    throw new Error(`registry policy value did not verify at ${CFT_WINDOWS_POLICY_KEY}`);
  }
}
