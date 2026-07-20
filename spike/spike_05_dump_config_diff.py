"""
Spike 05 — Dump launch_options config 2 times, diff to find which keys are
randomized per-launch (root cause of canvas signature drift in spike_04).

Hypothesis (from reading camoufox/utils.py:launch_options):
  - set_into('fonts:spacing_seed', randint)  — pre-set by user → no-op (good)
  - 'fonts' not in config → _generate_random_font_subset(os) (RANDOM per launch!)
  - 'voices' not in config → _generate_random_voice_subset(os) (RANDOM)
  - set_media_devices_defaults → RANDOM mic/camera deviceIds
  - set_into('window.history.length', randrange(1,6))  → only no-op if pre-set

Strategy: dump config twice, JSON-diff keys whose values differ. Then build
a fully frozen config (fonts/voices/window.history.length + seeds all
pre-persisted) and confirm canvas signature becomes stable.
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

# Import after env loaded
from camoufox.utils import launch_options
from camoufox.fingerprints import from_browserforge
from browserforge.fingerprints import FingerprintGenerator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike_04_stable_seeds import reconstruct_fp  # reuse

SPIKE_DIR = Path(__file__).resolve().parent
FP_PATH = SPIKE_DIR / "fingerprint_seed.json"
SEEDS_PATH = SPIKE_DIR / "seeds.json"
OUT_DIR = SPIKE_DIR / "out"; OUT_DIR.mkdir(exist_ok=True)


def fixed_proxy():
    h, p, u, pw = (os.environ[f"PROXY_1_{k}"] for k in ("HOST", "PORT", "USER", "PASS"))
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}


def dump_opts(tag: str, extra_config: dict | None = None) -> dict:
    """Call launch_options() with the same args spike_04 uses, return final config."""
    fp_dict = json.loads(FP_PATH.read_text())
    fp_obj = reconstruct_fp(fp_dict)
    seeds = json.loads(SEEDS_PATH.read_text())

    base_config = from_browserforge(fp_obj)
    base_config.update(seeds)
    if extra_config:
        base_config.update(extra_config)

    # We can't capture config directly since launch_options returns a play-
    # wright dict; but `debug=True` prints the config. Instead, replicate the
    # randomization by running launch_options with a throwaway proxy test:
    # actually launch_options returns the playwright launch dict, but the
    # camoufox config is built INTO it under env CAMOU_CONFIG_1. Trap it via
    # monkeypatch of set_into / merge_into to capture the final config.
    return _captured_config(fp_obj, base_config, fixed_proxy())


def _captured_config(fp_obj, base_config, proxy) -> dict:
    """Run launch_options with patched set_into to snapshot final config."""
    import camoufox.utils as U
    captured = {}
    real_set_into = U.set_into
    real_merge_into = U.merge_into

    # Wrap set_into to track what's written after user pre-set
    def tracking_set_into(target, key, value):
        real_set_into(target, key, value)
        captured[key] = target[key]
    U.set_into = tracking_set_into

    # merge_into copies source→target only if key not in target,
    # so it does nothing for pre-set keys; track what merge_into writes that's NEW
    def tracking_merge_into(target, source):
        for k, v in source.items():
            if k not in target:
                target[k] = v
                captured[f"[merge]{k}"] = v
    U.merge_into = tracking_merge_into

    try:
        opts = launch_options(
            headless=True,
            fingerprint=fp_obj,
            i_know_what_im_doing=True,
            proxy=proxy,
            geoip=True,
            block_webrtc=True,
            config=deepcopy(base_config),
            debug=False,
        )
    finally:
        U.set_into = real_set_into
        U.merge_into = real_merge_into

    # also pull the full config out of opts if exposed; camoufox builds CAMOU_CONFIG env
    # in opts['env']. Try both.
    env_cfg = None
    if isinstance(opts, dict):
        env = opts.get("env") or {}
        for k, v in env.items():
            if k.startswith("CAMOU_CONFIG"):
                env_cfg = (k, v)
                break
    return {"tracked_writes": captured, "env_config_key": env_cfg, "opts_keys": list(opts.keys()) if isinstance(opts, dict) else None}


def main():
    c1 = dump_opts("run1")
    c2 = dump_opts("run2")
    OUT_DIR.joinpath("cfg_diff_base_run1.json").write_text(json.dumps(c1, indent=2, default=str))
    OUT_DIR.joinpath("cfg_diff_base_run2.json").write_text(json.dumps(c2, indent=2, default=str))

    w1, w2 = c1["tracked_writes"], c2["tracked_writes"]
    keys = set(w1.keys()) | set(w2.keys())
    print(f"\n=== DIFF set_into/merge_into writes (run1 vs run2) ===")
    drift_keys = []
    for k in sorted(keys):
        v1 = w1.get(k, "<missing>")
        v2 = w2.get(k, "<missing>")
        if v1 != v2:
            drift_keys.append(k)
            s1 = str(v1)[:80]
            s2 = str(v2)[:80]
            print(f"  DRIFT  {k}:")
            print(f"    r1: {s1}")
            print(f"    r2: {s2}")
        else:
            print(f"  same   {k}: {str(v1)[:60]}")

    print(f"\n=== DRIFT KEYS ({len(drift_keys)}) ===")
    for k in drift_keys:
        print(f"  - {k}")

    # Also dump env CAMOU_CONFIG if present
    if c1["env_config_key"]:
        key, val = c1["env_config_key"]
        print(f"\n=== {key} (run1) — first 500 chars ===")
        print(str(val)[:500])
        OUT_DIR.joinpath("cfg_camou_config_run1.json").write_text(str(val))


if __name__ == "__main__":
    main()
