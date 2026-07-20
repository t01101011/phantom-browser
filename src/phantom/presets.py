"""Platform presets — per-platform fingerprint + warm-up defaults.

Fingerprint determinism (the 6-blob lock) is the same for every platform.
What changes per preset:
  * {target_os, screen constraints, navigator.language, locale.region}
  * whether a mobile profile is used (TikTok sometimes requires mobile)
  * proxy quality expectations (residential mandatory for fb/tiktok)
  * warm-up pacing (numbered stages not yet implemented — placeholder here)

A preset returns a dict of PROFILE-LEVEL defaults that feed into the
identity generator + the launch config. The fingerprint blobs themselves
are always generated once, persisted, never regenerated (see SKILL.md).

We currently always spoof `windows` because:
  - Camoufox WebGL DB + BrowserForge fingerprints for `os='windows'` are the
    most complete.
  - tk's real target machine is Windows.
Mobile profiles are a TODO for Phase 3 (TikTok mobile canvas probes).
"""
from __future__ import annotations
from typing import Optional

PRESETS: dict[str, dict] = {
    "facebook": {
        "platform_tag": "facebook",
        "target_os": "windows",
        "locale_region": "US",
        "navigator_language": "en-US",
        "timezone_default": None,          # GeoIP from proxy
        "proxy_required": True,
        "proxy_kind": "residential",       # datacenter dies instantly on FB
        "notes_default": "FB: residential proxy, warm slowly, keep cookie stable",
    },
    "tiktok": {
        "platform_tag": "tiktok",
        "target_os": "windows",             # mobile profile = Phase 3 TODO
        "locale_region": "US",
        "navigator_language": "en-US",
        "timezone_default": None,
        "proxy_required": True,
        "proxy_kind": "residential",        # canvas/WebGL/device-motion probes
        "notes_default": "TikTok: residential, canvas probing, may need mobile profile",
    },
    "chatgpt": {
        "platform_tag": "chatgpt",
        "target_os": "windows",
        "locale_region": "US",
        "navigator_language": "en-US",
        "timezone_default": None,
        "proxy_required": True,
        "proxy_kind": "residential",        # login may demand SMS verify
        "notes_default": "ChatGPT: IP + cookie, SMS verify risk when IP shared",
    },
    "custom": {
        "platform_tag": "custom",
        "target_os": "windows",
        "locale_region": "US",
        "navigator_language": "en-US",
        "timezone_default": None,
        "proxy_required": False,
        "proxy_kind": None,
        "notes_default": "",
    },
}


def get_preset(platform_tag: str) -> dict:
    """Return preset or raise. 'custom' is the fallback."""
    if platform_tag not in PRESETS:
        raise ValueError(
            f"Unknown platform_tag {platform_tag!r}. "
            f"Must be one of: {list(PRESETS.keys())}"
        )
    return PRESETS[platform_tag]
