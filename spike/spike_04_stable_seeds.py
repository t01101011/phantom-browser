"""
Spike 04 — Stable canvas/audio/font seeds per profile.

In spike 03 we saw Canvas signature change between runs (E3D98D → 74F0FB → 8D1DA).
That's because Camoufox calls randint() per-launch for canvas:seed / audio:seed /
fonts:spacing_seed, and silently increments them if not already set in config.

Fix: pass `config={'canvas:seed': N, 'audio:seed': N, 'fonts:spacing_seed': N}`
alongside the fingerprint. Persist those numbers per profile.

Goal: verify
- Canvas signature STABLE across 2 launches with same seeds
- WebGL still disabled (Linux headless) or working (log it)
- block_webrtc=True hides real IP from WebRTC
- Override timezone explicitly (avoid Denver vs Chicago mismatch)
"""
from __future__ import annotations
import json, os, sys, time, hashlib
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
for line in ENV_PATH.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v.strip()

from camoufox.sync_api import Camoufox
from browserforge.fingerprints import FingerprintGenerator
from camoufox.fingerprints import from_browserforge

FP_PATH = Path(__file__).resolve().parent / "fingerprint_seed.json"
SEEDS_PATH = Path(__file__).resolve().parent / "seeds.json"
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(exist_ok=True)

def reconstruct_fp(fp_dict):
    from browserforge.fingerprints import (
        Fingerprint, NavigatorFingerprint, ScreenFingerprint, VideoCard,
    )
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

def load_or_create():
    """Load or create fingerprint + persistent seeds."""
    if not FP_PATH.exists():
        fg = FingerprintGenerator(browser="firefox", os="windows")
        fp = fg.generate()
        FP_PATH.write_text(fp.dumps())
        print(f"[+] Generated new fingerprint ({len(fp.dumps())} bytes)")
    fp_dict = json.loads(FP_PATH.read_text())

    if not SEEDS_PATH.exists():
        # Fixed seeds — these are the "identity" of this profile
        # Use range [1, 2^32-1] to avoid the no-op value 0
        import random
        rng = random.Random(0xBADC0FFEE)  # fixed rng for spike (real use: per-profile random then stored)
        seeds = {
            "canvas:seed": rng.randint(1, 2**32 - 1),
            "audio:seed": rng.randint(1, 2**32 - 1),
            "fonts:spacing_seed": rng.randint(1, 2**32 - 1),
        }
        SEEDS_PATH.write_text(json.dumps(seeds, indent=2))
        print(f"[+] Generated new seeds: {seeds}")
    seeds = json.loads(SEEDS_PATH.read_text())
    return reconstruct_fp(fp_dict), seeds

def proxy_dict(idx: int) -> dict:
    h = os.environ[f"PROXY_{idx}_HOST"]
    p = os.environ[f"PROXY_{idx}_PORT"]
    u = os.environ[f"PROXY_{idx}_USER"]
    pw = os.environ[f"PROXY_{idx}_PASS"]
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}

def run(proxy_idx: int, tag: str, fp_obj, seeds: dict):
    print(f"\n=== {tag} | proxy {proxy_idx} | seeds={seeds} ===")
    # Build our own config first, then pass through config= so set_into is a no-op
    config = from_browserforge(fp_obj)
    config.update(seeds)
    # also try forcing a WebGL renderer to test spoof path (may not work on headless linux)
    # config['webGl:vendor'] = 'Google Inc. (NVIDIA)'
    # config['webGl:renderer'] = 'ANGLE (NVIDIA, NVIDIA GeForce GTX 980 Direct3D11 vs_5_0 ps_5_0)'

    seeds_index = [seeds['canvas:seed'], seeds['audio:seed'], seeds['fonts:spacing_seed']]
    with Camoufox(
        headless=True,
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=proxy_dict(proxy_idx),
        geoip=True,
        block_webrtc=True,            # hide real IP from WebRTC entirely
        config=config,
        debug=True,                   # log config — check Camoufox receives our seeds
    ) as browser:
        context = browser.new_context() if hasattr(browser, "new_context") else browser
        page = context.new_page()

        # exit IP
        page.goto("http://ip-api.com/json?fields=query,country,city,timezone", timeout=30000, wait_until="domcontentloaded")
        ip = page.evaluate("() => document.body.innerText")
        print(f"[+] Exit IP: {ip}")

        # canvas + webgl signature via browserleaks/canvas
        page.goto("https://browserleaks.com/canvas", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        canvas_info = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('tr'));
            const out = {};
            rows.forEach(tr => {
                const tds = tr.querySelectorAll('td');
                if (tds.length === 2) out[tds[0].innerText.trim()] = tds[1].innerText.trim();
            });
            return out;
        }""")
        sig = canvas_info.get("Signature", "?")
        print(f"[+] Canvas signature: {sig}")
        print(f"    Uniqueness: {canvas_info.get('Uniqueness', '?')}")

        # webgl page
        page.goto("https://browserleaks.com/webgl", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        webgl_info = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('tr'));
            const out = {};
            rows.forEach(tr => {
                const tds = tr.querySelectorAll('td');
                if (tds.length === 2) out[tds[0].innerText.trim()] = tds[1].innerText.trim();
            });
            return out;
        }""")
        print(f"[+] WebGL Vendor: {webgl_info.get('Unmasked Vendor', '?')}")
        print(f"[+] WebGL Renderer: {webgl_info.get('Unmasked Renderer', '?')}")
        print(f"[+] WebGL Supported: {webgl_info.get('This browser supports WebGL', '?')}")

        # self-report
        probe = page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                language: navigator.language,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'null',
                webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'null',
            };
        }""")
        print(f"[+] Self: {json.dumps(probe)}")
        (OUT_DIR / f"{tag}.json").write_text(json.dumps({
            "ip": ip, "canvas": canvas_info, "webgl": webgl_info, "self": probe,
        }, indent=2))

if __name__ == "__main__":
    fp, seeds = load_or_create()
    run(1, "run1_proxy1", fp, seeds)
    run(1, "run2_proxy1", fp, seeds)
    run(2, "run3_proxy2", fp, seeds)

    # Compare canvas signatures
    print("\n=== CANVAS SIGNATURE COMPARISON ===")
    sigs = {}
    for tag in ["run1_proxy1", "run2_proxy1", "run3_proxy2"]:
        data = json.loads((OUT_DIR / f"{tag}.json").read_text())
        sigs[tag] = data["canvas"].get("Signature")
    for k, v in sigs.items():
        print(f"  {k}: {v}")
    if len(set(sigs.values())) == 1:
        print("  ✅ Canvas signature STABLE across runs — fingerprint now truly persistent!")
    else:
        print("  ⚠️ canvas still moving — need to dig deeper")
