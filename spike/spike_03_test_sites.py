"""
Spike 03 — Verify Camoufox spoof on real fingerprint test sites.

Sites:
  - https://abrahamjuliot.github.io/creepjs/        — comprehensive fingerprint detector
  - https://browserleaks.com/canvas                 — canvas hash
  - https://browserleaks.com/webgl                  — WebGL vendor/renderer

Goal: verify Camoufox actually spoofs fingerprint on real pages (not about:blank).
"""
from __future__ import annotations
import json, os, sys, time
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

def proxy_dict(idx: int) -> dict:
    h = os.environ[f"PROXY_{idx}_HOST"]
    p = os.environ[f"PROXY_{idx}_PORT"]
    u = os.environ[f"PROXY_{idx}_USER"]
    pw = os.environ[f"PROXY_{idx}_PASS"]
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}

def run(proxy_idx: int, tag: str):
    fp_dict = json.loads(FP_PATH.read_text())
    fp_obj = reconstruct_fp(fp_dict)

    print(f"\n=== {tag} | proxy {proxy_idx} ===")
    with Camoufox(
        headless=True,
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=proxy_dict(proxy_idx),
        geoip=True,
    ) as browser:
        context = browser.new_context() if hasattr(browser, "new_context") else browser
        page = context.new_page()

        # --- browserleaks/webgl: cleanest signal for WebGL spoof ---
        print("[*] browserleaks.com/webgl")
        try:
            page.goto("https://browserleaks.com/webgl", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            # Vendor/Renderer shown in tables
            webgl_info = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr'));
                const out = {};
                rows.forEach(tr => {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length === 2) out[tds[0].innerText.trim()] = tds[1].innerText.trim();
                });
                return out;
            }""")
            print("    WebGL info:", json.dumps(webgl_info, ensure_ascii=False)[:600])
            page.screenshot(path=str(OUT_DIR / f"{tag}_webgl.png"), full_page=True)
        except Exception as e:
            print("    failed:", type(e).__name__, str(e)[:200])

        # --- browserleaks/canvas: hash
        print("[*] browserleaks.com/canvas")
        try:
            page.goto("https://browserleaks.com/canvas", timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            canvas_info = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr'));
                const out = {};
                rows.forEach(tr => {
                    const tds = tr.querySelectorAll('td');
                    if (tds.length === 2) out[tds[0].innerText.trim()] = tds[1].innerText.trim();
                });
                return out;
            }""")
            print("    Canvas info:", json.dumps(canvas_info, ensure_ascii=False)[:600])
            page.screenshot(path=str(OUT_DIR / f"{tag}_canvas.png"), full_page=True)
        except Exception as e:
            print("    failed:", type(e).__name__, str(e)[:200])

        # --- creepjs: full fingerprint score (heavy JS, wait longer)
        print("[*] creepjs (heavy)")
        try:
            page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(8000)  # creepjs computes async
            # The trust score / fingerprint
            score_text = page.evaluate("""() => {
                const el = document.querySelector('.trust-score, [class*=\"trust\"]');
                if (el) return el.innerText;
                // fallback: grab visible body text snippet
                const t = document.body.innerText || '';
                return t.slice(0, 2000);
            }""")
            print("    CreepJS snippet:")
            for line in score_text.split("\n")[:25]:
                if line.strip():
                    print("      " + line.strip()[:150])
            page.screenshot(path=str(OUT_DIR / f"{tag}_creepjs.png"), full_page=True)
        except Exception as e:
            print("    failed:", type(e).__name__, str(e)[:200])

        # Browser-reported values (for cross-check)
        probe = page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'null',
                webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'null',
            };
        }""")
        print("    Browser self-report:", json.dumps(probe, ensure_ascii=False))
        # write the probe so we can compare across runs/proxies
        (OUT_DIR / f"{tag}_probe.json").write_text(json.dumps(probe, indent=2))

if __name__ == "__main__":
    run(1, "run1_proxy1")
    run(1, "run2_proxy1")
    run(2, "run3_proxy2")
    print("\n=== OUT FILES ===")
    for f in sorted(OUT_DIR.iterdir()):
        print(f" ", f.name, f.stat().st_size, "bytes")
