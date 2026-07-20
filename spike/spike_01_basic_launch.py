"""
Spike 01 — Launch Camoufox headless, dump fingerprint, verify persistence.

Goal: verify
- Camoufox engine runs on Linux headless
- BrowserForge fingerprint generates + serializes to JSON
- Same fingerprint obj → same Camoufox config (deterministic)
- Browser loads a test page and we can extract UA + WebGL vendor
"""
from __future__ import annotations
import json, sys, hashlib, time
from pathlib import Path

from camoufox.sync_api import Camoufox
from browserforge.fingerprints import FingerprintGenerator
from camoufox.fingerprints import from_browserforge

# --- Config ---
PROFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

FP_PATH = Path(__file__).resolve().parent / "fingerprint_seed.json"

def gen_or_load_fingerprint() -> dict:
    """Generate once, persist JSON, reload on next run. Returns Camoufox config dict."""
    if FP_PATH.exists():
        print(f"[+] Loading existing fingerprint from {FP_PATH}")
        fp_json = FP_PATH.read_text()
    else:
        print(f"[+] Generating new BrowserForge fingerprint (Firefox/Windows)")
        fg = FingerprintGenerator(browser='firefox', os='windows')
        fp = fg.generate()
        fp_json = fp.dumps()
        FP_PATH.write_text(fp_json)
        print(f"    Saved → {FP_PATH}  ({len(fp_json)} bytes)")

    # Hash for "deterministic" check
    h = hashlib.sha256(fp_json.encode()).hexdigest()[:16]
    print(f"    Fingerprint JSON sha256[:16] = {h}")
    return json.loads(fp_json)

def reconstruct_fingerprint_obj(fp_dict: dict):
    """Reconstruct a BrowserForge Fingerprint from a plain dict.

    BrowserForge's Fingerprint class doesn't have a from_dict/loads helper,
    so we manually rebuild nested dataclasses.
    """
    from browserforge.fingerprints import (
        Fingerprint, NavigatorFingerprint, ScreenFingerprint, VideoCard,
    )
    nav = NavigatorFingerprint(**fp_dict['navigator'])
    screen = ScreenFingerprint(**fp_dict['screen'])
    vc = fp_dict.get('videoCard')
    video_card = VideoCard(**vc) if vc else None
    return Fingerprint(
        screen=screen,
        navigator=nav,
        headers=fp_dict['headers'],
        videoCodecs=fp_dict['videoCodecs'],
        audioCodecs=fp_dict['audioCodecs'],
        pluginsData=fp_dict['pluginsData'],
        battery=fp_dict.get('battery'),
        videoCard=video_card,
        multimediaDevices=fp_dict['multimediaDevices'],
        fonts=fp_dict['fonts'],
        mockWebRTC=fp_dict.get('mockWebRTC'),
        slim=fp_dict.get('slim'),
    )

def launch_and_probe(headless: bool = True, geoip: bool = True):
    """Launch Camoufox, return probe dict with what the browser actually reports."""
    fp_dict = gen_or_load_fingerprint()
    fp_obj = reconstruct_fingerprint_obj(fp_dict)

    cfg = from_browserforge(fp_obj)
    print(f"[+] Camoufox config keys: {sorted(cfg.keys())[:8]}…  ({len(cfg)} keys total)")

    print(f"[+] Launching Camoufox (headless={headless}, geoip={geoip})")
    with Camoufox(headless=headless, fingerprint=fp_obj, geoip=geoip) as browser:
        context = browser.new_context() if hasattr(browser, 'new_context') else browser
        page = context.new_page()
        print(f"[+] Opened page, navigating to test URL")
        page.goto("about:blank", wait_until="load", timeout=15000)
        probe = page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                oscpu: navigator.oscpu,
                language: navigator.language,
                languages: navigator.languages,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                maxTouchPoints: navigator.maxTouchPoints,
                screen: { w: screen.width, h: screen.height, dpr: screen.devicePixelRatio },
                webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
                webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                plugins: Array.from(navigator.plugins).map(p => p.name),
            };
        }""")
        # also capture timezone offset, battery (not critical), etc.
    return probe

def main():
    print("=" * 60)
    print("SPIKE 01 — Camoufox basic launch + fingerprint persistence")
    print("=" * 60)
    # Run 1
    print("\n--- RUN 1 ---")
    t0 = time.time()
    probe1 = launch_and_probe(headless=True, geoip=True)
    t1 = time.time()
    print(f"[+] Run 1 took {t1-t0:.1f}s")
    print(json.dumps(probe1, indent=2))

    # Run 2 — should be IDENTICAL because we loaded same fingerprint
    print("\n--- RUN 2 (same fingerprint) ---")
    t0 = time.time()
    probe2 = launch_and_probe(headless=True, geoip=True)
    t1 = time.time()
    print(f"[+] Run 2 took {t1-t0:.1f}s")
    print(json.dumps(probe2, indent=2))

    # Compare
    print("\n--- DETECTED-VALUE DIFF ---")
    diffs = []
    for k in set(probe1.keys()) | set(probe2.keys()):
        v1 = probe1.get(k)
        v2 = probe2.get(k)
        if v1 != v2:
            diffs.append((k, v1, v2))
            print(f"  {k}: {v1!r} ≠ {v2!r}")
    if not diffs:
        print("  ✅ identical across runs (fingerprint deterministic)")
    else:
        print(f"  ⚠️ {len(diffs)} field(s) changed between runs")
    print("\nDone.")

if __name__ == "__main__":
    sys.exit(main() or 0)
