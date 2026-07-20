#!/usr/bin/env python3
"""Evaluate a normalized Task16 report and write a checksummed safe artifact."""
import argparse
import json
from pathlib import Path
from phantom.stealth import canonical_bytes, checksum, load_and_evaluate

p=argparse.ArgumentParser()
p.add_argument("report")
p.add_argument("--output", default="stealth-coherence-result.json")
p.add_argument("--require-complete", action="store_true", help="fail if any optional surface is unsupported")
a=p.parse_args()
safe, verdict=load_and_evaluate(a.report)
artifact: dict[str, object]={"report": safe, "verdict": verdict}
artifact["checksum_sha256"]=checksum(artifact)
Path(a.output).write_bytes(canonical_bytes(artifact))
print(json.dumps({"status":verdict["status"],"counts":verdict["counts"],"checksum_sha256":artifact["checksum_sha256"]},sort_keys=True))
raise SystemExit(1 if verdict["status"]=="fail" or (a.require_complete and verdict["status"]!="pass") else 0)
