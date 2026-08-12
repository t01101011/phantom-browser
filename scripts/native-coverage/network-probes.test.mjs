import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { runNetworkAdapters } from "./network-probes.mjs";

const RUN_ID = "11111111-1111-4111-8111-111111111111";
const PROVENANCE = {
  engine: "cft",
  binarySha256: "a".repeat(64),
  platform: "linux/x64",
  runId: RUN_ID,
};

test("packet-level surfaces stay UNKNOWN when capture is unavailable", async () => {
  const result = await runNetworkAdapters();
  for (const item of Object.values(result)) assert.equal(item.status, "UNKNOWN");
});

test("controlled parsed evidence is imported while unsupported claims normalize to UNKNOWN", async () => {
  const directory = await mkdtemp(join(tmpdir(), "phantom-network-evidence-"));
  const path = join(directory, "evidence.json");
  await writeFile(
    path,
    JSON.stringify({
      schemaVersion: 1,
      ...PROVENANCE,
      tlsJa3Ja4: { status: "OBSERVED", method: "controlled-pcap", value: { ja3: "digest" } },
      http2Settings: { status: "PASS", method: "launch-flag", value: true },
    }),
  );
  try {
    const result = await runNetworkAdapters({ evidencePath: path, provenance: PROVENANCE });
    assert.equal(result.tlsJa3Ja4.status, "OBSERVED");
    assert.equal(result.http2Settings.status, "UNKNOWN");
    assert.equal(result.http3Quic.status, "UNKNOWN");
    assert.equal(result.dns.status, "UNKNOWN");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("rejects parsed evidence from another engine, binary, or run", async () => {
  const directory = await mkdtemp(join(tmpdir(), "phantom-network-evidence-"));
  const path = join(directory, "evidence.json");
  await writeFile(path, JSON.stringify({ schemaVersion: 1, ...PROVENANCE }));
  try {
    await assert.rejects(
      runNetworkAdapters({
        evidencePath: path,
        provenance: {
          engine: "cloakbrowser",
          binarySha256: "b".repeat(64),
          platform: "linux/x64",
          runId: "22222222-2222-4222-8222-222222222222",
        },
      }),
      /provenance does not match/,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
