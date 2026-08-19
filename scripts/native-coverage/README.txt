Phantom native Chromium coverage harness

Purpose
- Capture page-visible runtime evidence separately for CFT and CloakBrowser.
- Never promote stored profile fields, launch flags, wrapper claims, or a successful URL load to PASS/native evidence.
- Emit JSON and a human summary containing engine tag/version, executable SHA-256, and platform.
- Keep unavailable packet-level evidence UNKNOWN.

Safe CFT smoke
  node scripts/native-coverage/run.mjs --engine cft

Explicit binary
  node scripts/native-coverage/run.mjs \
    --engine cft \
    --binary /path/to/chrome \
    --output artifacts/native-coverage/cft.json \
    --summary artifacts/native-coverage/cft.txt

CloakBrowser
  node scripts/native-coverage/run.mjs \
    --engine cloakbrowser \
    --binary /licensed/path/to/chrome \
    --release-tag <locked-tag> \
    --binary-sha256 <publisher-verified-sha256>

The harness never downloads CloakBrowser or any proprietary asset. CloakBrowser runs require a release tag and independently publisher-verified binary SHA-256; a generic Chromium executable cannot be relabelled without matching that pinned digest. Run CFT and CloakBrowser separately; one engine's evidence is never copied to the other.

Network boundary
TLS JA3/JA4, HTTP/2 SETTINGS, HTTP/3/QUIC, and DNS need an approved controlled endpoint and/or packet parser. --capture --interface only records adapter availability; without parsed packets the result deliberately remains UNKNOWN. A controlled observer can provide a <=1 MiB JSON file via --network-evidence together with --run-id. It must include schemaVersion=1 plus the exact engine, binarySha256, platform, and runId from this run, then use the same evidence envelopes as the main report, for example {"tlsJa3Ja4":{"status":"OBSERVED","method":"controlled-pcap","value":{"ja3":"..."}}}; stale, cross-engine, missing, or non-OBSERVED evidence is rejected or normalizes to UNKNOWN. Proxy routing likewise stays UNKNOWN unless a controlled egress observer is explicitly integrated. This avoids turning flags, stored proxy fields, or third-party echo services into false proof.

Tests
  node --test scripts/native-coverage/evidence.test.mjs

Output files are mode 0600 and recursively redact common credential-bearing keys. Do not pass credentials in --browser-arg; process arguments are visible to the host OS.
