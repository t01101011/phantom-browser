"""Per-profile fingerprint identity generator.

Port of spike_06 (verified 48/48 config keys byte-identical across 2 launches)
into a reusable module. Generates the 6 persistent blobs once per profile:

    fingerprint_json   — BrowserForge Fingerprint.dumps()
    seeds_json         — {canvas:seed, audio:seed, fonts:spacing_seed}
    webgl_json         — sample_webgl(target_os) dict (vendor/renderer locked)
    fonts_json         — _generate_random_font_subset(target_os)
    voices_json        — _generate_random_voice_subset(target_os)
    misc_json          — {window.history.length, window.screenY}

These 6 blobs are stored in the DB and together reconstruct the SAME
identity on every launch. launch_options() random fields are all pre-set
in `config=` so its internal randint/sample paths no-op.

BrowserForge has no `Fingerprint.loads()`, only `dumps()` → reconstruction
must be manual. Reference: spike_04_stable_seeds.py:reconstruct_fp().
"""
from __future__ import annotations
import json
import random
from typing import Any

from browserforge.fingerprints import (
    Fingerprint, FingerprintGenerator, NavigatorFingerprint,
    ScreenFingerprint, VideoCard,
)
from camoufox.fingerprints import (
    from_browserforge, _generate_random_font_subset,
    _generate_random_voice_subset,
)
from camoufox.webgl import sample_webgl

FF_VERSION = "152"   # must match installed Camoufox binary (v152.0.4-beta.28)


def reconstruct_fp(fp_dict: dict) -> Fingerprint:
    """Rebuild a BrowserForge Fingerprint dataclass from its dumps() JSON.

    Direct port of the verified helper from spike_04/spike_06. No
    `Fingerprint.loads` exists upstream, so we walk nested dataclasses.
    """
    nav = NavigatorFingerprint(**fp_dict["navigator"])
    screen = ScreenFingerprint(**fp_dict["screen"])
    vc = fp_dict.get("videoCard")
    video_card = VideoCard(**vc) if vc else None
    return Fingerprint(
        screen=screen, navigator=nav, headers=fp_dict["headers"],
        videoCodecs=fp_dict["videoCodecs"], audioCodecs=fp_dict["audioCodecs"],
        pluginsData=fp_dict["pluginsData"], battery=fp_dict.get("battery"),
        videoCard=video_card, multimediaDevices=fp_dict["multimediaDevices"],
        fonts=fp_dict["fonts"], mockWebRTC=fp_dict.get("mockWebRTC"),
        slim=fp_dict.get("slim"),
    )


def _map_target_os(target_os: str) -> str:
    """Map our target_os values to the 3-arg forms camoufox/browserforge expect."""
    return {
        "windows": "windows",
        "macos":   "macos",
        "linux":   "linux",
    }.get(target_os, "windows")


def generate_identity(target_os: str = "windows") -> dict[str, Any]:
    """Generate all 6 persistent blobs for one new profile.

    Returns dict with keys: fingerprint_json, seeds_json, webgl_json,
    fonts_json, voices_json, misc_json (all JSON-serialised strings).
    """
    bf_os  = _map_target_os(target_os)              # browserforge os kwarg
    cam_os = bf_os[:3] if bf_os in ("windows", "linux", "macos") else "win"
    # camoufox sample_webgl / _generate_random_font_subset use 'win' | 'mac' | 'lin'
    CAM_OS = {"windows": "win", "macos": "mac", "linux": "lin"}[target_os]

    # 1. BrowserForge fingerprint — once. (No seed API upstream; we persist JSON.)
    fp = FingerprintGenerator(browser="firefox", os=bf_os).generate()
    fp_json = fp.dumps()
    fp_dict = json.loads(fp_json)

    # 2. Seeds — random.uint32, persisted. These feed canvas/audio/font spacing noise.
    rng = random.Random()  # /dev/urandom-backed; we want per-profile uniqueness
    seeds = {
        "canvas:seed":        rng.randint(1, 2**32 - 1),
        "audio:seed":         rng.randint(1, 2**32 - 1),
        "fonts:spacing_seed": rng.randint(1, 2**32 - 1),
    }

    # 3. WebGL identity — sample_webgl(CAM_OS) returns a full dict with
    #    {webGl:vendor, webGl:renderer, webGl:parameters, webGl2:parameters...}.
    #    Lock all of it so launch_options() never enters its random
    #    sample_webgl(target_os) path (root cause of BUG-1).
    webgl = sample_webgl(CAM_OS)
    webgl.pop("webGl2Enabled", None)

    # 4. Fonts list — _generate_random_font_subset per-launch when 'fonts'
    #    not pre-set → randomises text rasterisation → canvas drift.
    fonts = _generate_random_font_subset(bf_os)

    # 5. Voices — identity consistency, cheap to lock.
    voices = _generate_random_voice_subset(bf_os)

    # 6. Misc window props — launch_options does randrange per-launch if
    #    not pre-set (handle_screenXY / set_into('window.history.length')).
    screen_dict = fp_dict["screen"]
    avail_h = int(screen_dict.get("availHeight", 1040))
    outer_h = int(screen_dict.get("outerHeight", 800))
    screenY_range = max(avail_h - outer_h, 1)
    misc = {
        "window.history.length": rng.randint(1, 5),
        "window.screenY":        rng.randint(0, screenY_range - 1),
    }

    return {
        "fingerprint_json": fp_json,
        "seeds_json":       json.dumps(seeds),
        "webgl_json":       json.dumps(webgl, default=str),
        "fonts_json":       json.dumps(fonts),
        "voices_json":      json.dumps(voices, default=str),
        "misc_json":        json.dumps(misc),
    }


def build_launch_config(
    profile: dict,
    headless: bool = True,
) -> tuple[Any, dict]:
    """Reconstruct the Fingerprint obj + build the full deterministic config.

    This is the heart of persistent identity: every random field in
    launch_options() is pre-set into `config=`, so its internal
    randint/sample_webgl/random_font_subset paths all no-op.

    Returns (Fingerprint obj, config_dict) ready to pass to Camoufox().
    """
    fp_obj = reconstruct_fp(json.loads(profile["fingerprint_json"]))
    seeds = json.loads(profile["seeds_json"])
    webgl = json.loads(profile["webgl_json"])
    fonts = json.loads(profile["fonts_json"])
    voices = json.loads(profile["voices_json"])
    misc = json.loads(profile["misc_json"])

    config = from_browserforge(fp_obj, ff_version=FF_VERSION)
    config.update(seeds)
    config.update(webgl)
    config["fonts"] = fonts
    config["voices"] = voices
    config.update(misc)

    tz = profile.get("timezone")
    if tz:
        config["timezone"] = tz   # wins over GeoIP (utils.py: setdefault)

    config["locale:language"]      = profile["locale_language"]
    config["locale:region"]        = profile["locale_region"]
    config["navigator.language"]   = profile["navigator_language"]
    config["navigator.languages"] = [profile["navigator_language"]]

    return fp_obj, config
