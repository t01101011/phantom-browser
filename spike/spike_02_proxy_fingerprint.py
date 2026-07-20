"""
Spike 02 — Launch Camoufox WITH proxy + fingerprint, verify geoip auto-matches.

Goal: verify
- Camoufox launches with proxy auth (user:pass)
- Exit IP = proxy IP (not server IP)
- geoip=True → timezone/locale auto-matched to proxy IP geo
- Same fingerprint + same proxy → same UA/WebGL/screen across 2 runs
- WebGL spoof works on real site (not about:blank)
"""
from __future__ import annotations
import json, os, sys, time, hashlib
from pathlib import Path
from urllib.parse import urlparse

# load .env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
for line in ENV_PATH.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v.strip()

from camoufox.sync_api import Camoufox
from browserforge.fingerprints import FingerprintGenerator
from camoufox.fingerprints import from_browserforge

FP_PATH = Path(__file__).resolve().parent / "fingerprint_seed.json"

def gen_or_load_fingerprint():
    if FP_PATH.exists():
        fp_json = FP_PATH.read_text()
        print(f"[+] Loaded existing fingerprint ({len(fp_json)} bytes)")
    else:
        print("[+] Generating new fingerprint (Firefox/Windows)")
        fg = FingerprintGenerator(browser="firefox", os="windows")
        fp = fg.generate()
        fp_json = fp.dumps()
        FP_PATH.write_text(fp_json)
    h = hashlib.sha256(fp_json.encode()).hexdigest()[:16]
    print(f"    fp sha256[:16] = {h}")
    return json.loads(fp_json)

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

def proxy_dict(idx: int) -> dict:
    h = os.environ[f"PROXY_{idx}_HOST"]
    p = os.environ[f"PROXY_{idx}_PORT"]
    u = os.environ[f"PROXY_{idx}_USER"]
    pw = os.environ[f"PROXY_{idx}_PASS"]
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}

def launch_probe(proxy_idx: int, label: str):
    print(f"\n{'='*60}\n[{label}] Proxy {proxy_idx} — {proxy_dict(proxy_idx)['server']}\n{'='*60}")
    fp_dict = gen_or_load_fingerprint()
    fp_obj = reconstruct_fp(fp_dict)

    cfg = from_browserforge(fp_obj)
    print(f"[+] Camoufox config: {len(cfg)} keys")

    print(f"[+] Launching with proxy + geoip=True…")
    t0 = time.time()
    with Camoufox(
        headless=True,
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=proxy_dict(proxy_idx),
        geoip=True,
    ) as browser:
        context = browser.new_context() if hasattr(browser, "new_context") else browser
        page = context.new_page()
        # Exit IP
        page.goto("http://ip-api.com/json?fields=query,country,city,timezone,isp,as", timeout=30000, wait_until="domcontentloaded")
        ip_text = page.evaluate("() => document.body.innerText")
        print(f"[+] Exit IP info: {ip_text}")
        # Browser probe (UA, WebGL, screen, timezone)
        page.goto("about:blank", wait_until="load")
        probe = page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                oscpu: navigator.oscpu,
                language: navigator.language,
                languages: navigator.languages,
                screen: { w: screen.width, h: screen.height },
                webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'no-webgl',
                webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'no-webgl',
                browserTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                timezoneOffset: new Date().getTimezoneOffset(),
            };
        }""")
        t1 = time.time()
        print(f"[+] Probe done in {t1-t0:.1f}s")
    return probe, ip_text

def main():
    # Two runs with same proxy + same fingerprint → check determinism + geoip match
    p1, ip1 = launch_probe(1, "RUN 1 — proxy 1")
    p2, ip2 = launch_probe(1, "RUN 2 — proxy 1 (determinism check)")

    print("\n--- PROBE 1 ---")
    print(json.dumps(p1, indent=2))
    print("\n--- PROBE 2 ---")
    print(json.dumps(p2, indent=2))

    print("\n--- DIFF ---")
    diffs = []
    for k in set(p1.keys()) | set(p2.keys()):
        if p1.get(k) != p2.get(k):
            diffs.append(k)
            print(f"  {k}: {p1.get(k)!r} ≠ {p2.get(k)!r}")
    if not diffs:
        print("  ✅ identical — fingerprint + proxy deterministic")

    # Now switch proxy → expect exit IP changes but fingerprint stays same (UA/WebGL/etc)
    p3, ip3 = launch_probe(2, "RUN 3 — proxy 2 (same fingerprint, diff proxy)")
    print("\n--- PROBE 3 (proxy 2, same fingerprint) ---")
    print(json.dumps(p3, indent=2))

    print("\n--- CROSS-PROXY FINGERPRINT CHECK ---")
    # UA/WebGL/screen should stay same; timezone/locale may shift to match new geo
    fp_fields = ["userAgent", "platform", "oscpu", "screen", "webglVendor", "webglRenderer"]
    for k in fp_fields:
        if p1.get(k) != p3.get(k):
            print(f"  ⚠️ {k} CHANGED across proxies: {p1.get(k)!r} → {p3.get(k)!r}")
        else:
            print(f"  ✅ {k} stable across proxies: {p1.get(k)!r}")

    # Timezone should match proxy exit geo (since both proxies exit at same location, expect same TZ)
    print(f"\n  proxy 1 IP geo TZ: {ip1}")
    print(f"  browser TZ (proxy 1): {p1['browserTimezone']}")
    print(f"  proxy 2 IP geo TZ: {ip3}")
    print(f"  browser TZ (proxy 2): {p3['browserTimezone']}")

if __name__ == "__main__":
    sys.exit(main() or 0)
