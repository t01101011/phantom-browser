"""
Spike 07 — Deep diff: dump the FULL final config (CAMOU_CONFIG_1 env var)
across 2 launches, JSON-diff EVERY key to find what still drifts after the
spike_06 fixes.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from copy import deepcopy

ENV = Path(__file__).resolve().parent.parent / ".env"
for line in ENV.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v.strip()

from camoufox.utils import launch_options
from camoufox.fingerprints import from_browserforge, _generate_random_font_subset, _generate_random_voice_subset
from camoufox.webgl import sample_webgl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike_04_stable_seeds import reconstruct_fp

SPIKE = Path(__file__).resolve().parent
FP_PATH = SPIKE / "fingerprint_seed.json"
SEEDS_PATH = SPIKE / "seeds.json"
WEBGL_PATH = SPIKE / "webgl.json"
FONTS_PATH = SPIKE / "fonts.json"
VOICES_PATH = SPIKE / "voices.json"
MISC_PATH = SPIKE / "misc.json"
OUT_DIR = SPIKE / "out"; OUT_DIR.mkdir(exist_ok=True)

FF_VERSION = "152"
TZ_OVERRIDE = "America/Denver"


def proxy_dict():
    h, p, u, pw = (os.environ[f"PROXY_1_{k}"] for k in ("HOST", "PORT", "USER", "PASS"))
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}


def get_full_config() -> dict:
    fp_dict = json.loads(FP_PATH.read_text())
    fp_obj = reconstruct_fp(fp_dict)
    seeds = json.loads(SEEDS_PATH.read_text())
    webgl = json.loads(WEBGL_PATH.read_text())
    fonts = json.loads(FONTS_PATH.read_text())
    voices = json.loads(VOICES_PATH.read_text())
    misc = json.loads(MISC_PATH.read_text())

    config = from_browserforge(fp_obj, ff_version=FF_VERSION)
    config.update(seeds)
    config.update(webgl)
    config["fonts"] = fonts
    config["voices"] = voices
    config.update(misc)
    config["timezone"] = TZ_OVERRIDE

    opts = launch_options(
        headless=True,
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=proxy_dict(),
        geoip=True,
        block_webrtc=True,
        config=deepcopy(config),
        debug=False,
    )
    # Extract final CAMOU_CONFIG from env
    env = opts.get("env", {})
    camou_cfg = None
    for k, v in env.items():
        if k.startswith("CAMOU_CONFIG"):
            camou_cfg = json.loads(v)
            break
    return camou_cfg or {}


def main():
    c1 = get_full_config()
    c2 = get_full_config()
    OUT_DIR.joinpath("full_cfg_run1.json").write_text(json.dumps(c1, indent=2, default=str))
    OUT_DIR.joinpath("full_cfg_run2.json").write_text(json.dumps(c2, indent=2, default=str))

    keys = sorted(set(c1.keys()) | set(c2.keys()))
    print(f"\n=== FULL CONFIG DIFF (run1 vs run2) ===\nTotal keys: {len(keys)}")
    drift = []
    for k in keys:
        v1 = c1.get(k, "<MISSING>")
        v2 = c2.get(k, "<MISSING>")
        s1 = json.dumps(v1, default=str, sort_keys=True)
        s2 = json.dumps(v2, default=str, sort_keys=True)
        if s1 != s2:
            drift.append(k)
            print(f"  DRIFT  {k}:")
            print(f"    r1: {s1[:120]}")
            print(f"    r2: {s2[:120]}")
    print(f"\n=== DRIFTED KEYS: {drift} ===")
    print(f"(stable keys: {len(keys) - len(drift)} / {len(keys)})")


if __name__ == "__main__":
    main()
