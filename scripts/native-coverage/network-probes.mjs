import { execFile } from "node:child_process";
import { open } from "node:fs/promises";
import { promisify } from "node:util";
import { normalizeEvidence, unknown } from "./evidence.mjs";

const execFileP = promisify(execFile);

async function commandExists(command) {
  try {
    await execFileP("sh", ["-c", `command -v ${command}`], { timeout: 1000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Network fingerprint capture is deliberately opt-in. A useful JA3/JA4 or
 * HTTP/2/QUIC result requires an approved capture interface or controlled
 * endpoint and packet parser. Merely seeing launch flags or a successful URL
 * load is not packet-level evidence.
 */
export async function runNetworkAdapters(options = {}) {
  if (options.evidencePath) {
    const handle = await open(options.evidencePath, "r");
    let raw;
    try {
      const metadata = await handle.stat();
      if (!metadata.isFile() || metadata.size > 1024 * 1024) {
        throw new Error("Network evidence must be a regular file no larger than 1 MiB");
      }
      const buffer = Buffer.alloc(1024 * 1024 + 1);
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
      if (bytesRead > 1024 * 1024) throw new Error("Network evidence exceeds 1 MiB");
      raw = buffer.subarray(0, bytesRead).toString("utf8");
    } finally {
      await handle.close();
    }
    const parsed = JSON.parse(raw);
    const expected = options.provenance;
    if (
      !expected ||
      parsed.schemaVersion !== 1 ||
      parsed.engine !== expected.engine ||
      parsed.binarySha256 !== expected.binarySha256 ||
      parsed.platform !== expected.platform ||
      parsed.runId !== expected.runId
    ) {
      throw new Error("Network evidence provenance does not match this browser run");
    }
    return Object.fromEntries(
      ["tlsJa3Ja4", "http2Settings", "http3Quic", "dns"].map((surface) => [
        surface,
        normalizeEvidence(surface, parsed[surface]),
      ]),
    );
  }
  const capture = options.capture ?? false;
  const iface = options.interface;
  const reason = capture
    ? "No approved capture interface/controlled parser was configured"
    : "Packet capture disabled; pass --capture --interface <name> only on an approved host";
  const adapter =
    capture && iface && (await commandExists("tcpdump")) ? `tcpdump:${iface}` : "not-observed";
  const result = {
    tlsJa3Ja4: unknown(reason, adapter),
    http2Settings: unknown(reason, adapter),
    http3Quic: unknown(reason, adapter),
    dns: unknown(
      "DNS routing needs a controlled resolver or packet capture; browser flags are not evidence",
      adapter,
    ),
  };
  return result;
}
