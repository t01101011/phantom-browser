"""
Spike 06 — Fix BUG-1 + BUG-2, verify canvas signature stable across 3 runs.

Root cause (from spike_05 diff + reading camoufox source):
  - from_browserforge(fp) does NOT set webGl:vendor / webGl:renderer from
    Fingerprint.videoCard — BrowserForge's videoCard field is not cast into
    webGl:vendor/webGl:renderer config keys by _cast_to_properties.
  - In launch_options() (utils.py:801-805), if webGl:vendor/renderer are
    missing, Camoufox calls sample_webgl(target_os) which RANDOMLY picks a
    WebGL vendor/renderer per launch — and the matching WebGL parameters
    drift too, which changes the canvas toDataURL() output.
  - set_into('window.history.length', randrange(1,6)) is also random per
    launch unless pre-set.

Fix:
  1. Persist webGl:vendor + webGl:renderer ONCE per profile (sample one
     record from the WebGL DB, lock it in). Same for window.history.length.
  2. Pass them in `config=` before launch_options() runs. Now
     launch_options() line 801 sees vendor+renderer pre-set → calls
     sample_webgl(target_os, vendor, renderer) which is deterministic (looks
     up that exact record).
  3. ff_version='152' passed to from_browserforge() so UA matches the
     binary's Firefox 152 (fixes BUG-2: UA said rv:150.0 before).
  4. Explicit timezone='America/Denver' (BUG-4 proxy geo) — override the
     GeoIP auto-pick that was landing on America/Chicago.

Expected: canvas signature IDENTICAL across 3 runs with same fingerprint +
          locked seeds + locked webgl + locked window.history.
"""
from __future__ import annotations
import json, os, sys, time, hashlib
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
for line in ENV.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v.strip()

from camoufox.sync_api import Camoufox
from camoufox.fingerprints import from_browserforge, _generate_random_font_subset, _generate_random_voice_subset
from camoufox.webgl import sample_webgl
from browserforge.fingerprints import FingerprintGenerator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike_04_stable_seeds import reconstruct_fp  # reuse same reconstruction

SPIKE = Path(__file__).resolve().parent
FP_PATH = SPIKE / "fingerprint_seed.json"
SEEDS_PATH = SPIKE / "seeds.json"
WEBGL_PATH = SPIKE / "webgl.json"          # NEW: persisted WebGL identity
FONTS_PATH = SPIKE / "fonts.json"          # NEW: persisted font list
VOICES_PATH = SPIKE / "voices.json"        # NEW: persisted voice list
MISC_PATH = SPIKE / "misc.json"            # NEW: window.history.length etc.
OUT_DIR = SPIKE / "out"; OUT_DIR.mkdir(exist_ok=True)

FF_VERSION = "152"   # matches the installed Camoufox binary v152.0.4-beta.28
TZ_OVERRIDE  = "America/Denver"   # proxy IP actually geo-resolves here
# GeoIP's locale selector picks a random language per-region per launch
# (locales.py:from_region → np.random.choice). We pin locale per-profile so
# it's stable. Proxy exits in US → en-US.
LOCALE_LANGUAGE = "en"
LOCALE_REGION   = "US"
NAVIGATOR_LANGUAGE = "en-US"


def load_or_create_identity():
    """Load or generate all the per-profile persistent values."""
    if not FP_PATH.exists():
        fg = FingerprintGenerator(browser="firefox", os="windows")
        FP_PATH.write_text(fg.generate().dumps())
    fp_dict = json.loads(FP_PATH.read_text())
    fp_obj = reconstruct_fp(fp_dict)

    if not SEEDS_PATH.exists():
        import random
        rng = random.Random(0xBADC0FFEE)
        SEEDS_PATH.write_text(json.dumps({
            "canvas:seed":        rng.randint(1, 2**32 - 1),
            "audio:seed":         rng.randint(1, 2**32 - 1),
            "fonts:spacing_seed": rng.randint(1, 2**32 - 1),
        }, indent=2))
    seeds = json.loads(SEEDS_PATH.read_text())

    # Generate + persist WebGL identity ONCE per profile (target_os='win'
    # because we spoof Windows). sample_webgl('win') returns a dict with
    # {webGl:vendor, webGl:renderer, webGl:parameters, webGl2:*, etc}. We
    # lock the vendor/renderer so future launches deterministically reuse
    # the same record (sample_webgl('win', vendor, renderer) is a lookup).
    if not WEBGL_PATH.exists():
        w = sample_webgl("win")
        w.pop("webGl2Enabled", None)
        WEBGL_PATH.write_text(json.dumps(w, indent=2, default=str))
        print(f"[+] Locked WebGL: vendor={w.get('webGl:vendor')!r} renderer={w.get('webGl:renderer')!r}")
    webgl = json.loads(WEBGL_PATH.read_text())

    # NEW: persist fonts list ONCE per profile. launch_options calls
    # _generate_random_font_subset('windows') per-launch when 'fonts' not in
    # config, which randomizes text rendering → canvas toDataURL changes.
    if not FONTS_PATH.exists():
        FONTS_PATH.write_text(json.dumps(_generate_random_font_subset("windows"), indent=2))
        print(f"[+] Locked fonts: {len(json.loads(FONTS_PATH.read_text()))} families")
    fonts = json.loads(FONTS_PATH.read_text())

    # NEW: persist voices list (does not affect canvas but is identity-level
    # consistency + cheap to lock)
    if not VOICES_PATH.exists():
        VOICES_PATH.write_text(json.dumps(_generate_random_voice_subset("windows"), indent=2, default=str))
    voices = json.loads(VOICES_PATH.read_text())

    if not MISC_PATH.exists():
        import random
        rng = random.Random(0xCAFEF00D)
        # Pick a stable screenY inside the available range so handle_screenXY
        # short-circuits via the "skip if manually provided" branch.
        screen_dict = json.loads(FP_PATH.read_text())["screen"]
        ah = screen_dict.get("availHeight", 1040)
        oh = screen_dict.get("outerHeight", 800)
        screenY_range = max(int(ah) - int(oh), 1)
        MISC_PATH.write_text(json.dumps({
            "window.history.length": rng.randint(1, 5),
            "window.screenY":        rng.randint(0, screenY_range - 1),
        }, indent=2))
        print(f"[+] Locked window.screenY range: [0,{screenY_range})")
    misc = json.loads(MISC_PATH.read_text())

    return fp_obj, seeds, webgl, fonts, voices, misc


def proxy_dict(idx: int) -> dict:
    h, p, u, pw = (os.environ[f"PROXY_{idx}_{k}"] for k in ("HOST", "PORT", "USER", "PASS"))
    return {"server": f"http://{h}:{p}", "username": u, "password": pw}


def run(proxy_idx: int, tag: str, fp_obj, seeds, webgl, fonts, voices, misc):
    print(f"\n=== {tag} | proxy {proxy_idx} ===")

    # Build the FULL deterministic config: BrowserForge-derived + seeds +
    # locked WebGL + locked misc. launch_options will set_into (no-op for
    # pre-set keys) and called sample_webgl(...) won't randomize because
    # webGl:vendor+webGl:renderer are already in config — but we bypass
    # even that by merging our full webgl dict directly.
    # Note: launch_options() itself has no `timezone=` param — timezone is a
    # config key. But `geoip=True` will overwrite config['timezone'] AFTER we
    # set it (geolocation.as_config → setdefault), so we need to *also* pass
    # it via... actually setdefault means OUR pre-set value WINS (setdefault
    # only sets if absent). Verified in utils.py:754-756: 'timezone' falls
    # into the setdefault branch → our value survives. Good.
    config = from_browserforge(fp_obj, ff_version=FF_VERSION)
    config.update(seeds)
    config.update(webgl)        # webGl:vendor, webGl:renderer, webGl:parameters, ...
    config["fonts"] = fonts
    config["voices"] = voices
    config.update(misc)         # window.history.length, window.screenY
    config["timezone"] = TZ_OVERRIDE
    # Pin locale so GeoIP's random language selection doesn't drift per launch
    config["locale:language"]       = LOCALE_LANGUAGE
    config["locale:region"]         = LOCALE_REGION
    config["navigator.language"]    = NAVIGATOR_LANGUAGE
    config["navigator.languages"]   = [NAVIGATOR_LANGUAGE]

    with Camoufox(
        headless="virtual",          # Xvfb — gives Firefox a real-ish display so the
                                     # canvas rasterizer doesn't drift per-process
        fingerprint=fp_obj,
        i_know_what_im_doing=True,
        proxy=proxy_dict(proxy_idx),
        geoip=True,
        block_webrtc=True,
        config=config,
        debug=False,
    ) as browser:
        context = browser.new_context() if hasattr(browser, "new_context") else browser
        page = context.new_page()

        page.goto("http://ip-api.com/json?fields=query,country,city,timezone", timeout=30000, wait_until="domcontentloaded")
        ip = page.evaluate("() => document.body.innerText")
        print(f"[+] Exit IP: {ip}")

        page.goto("https://browserleaks.com/canvas", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        canvas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('tr'));
            const out = {};
            rows.forEach(tr => {
                const tds = tr.querySelectorAll('td');
                if (tds.length === 2) out[tds[0].innerText.trim()] = tds[1].innerText.trim();
            });
            return out;
        }""")
        sig = canvas.get("Signature", "?")
        print(f"[+] Canvas signature: {sig}")

        # self probe (UA, tz, webGL)
        probe = page.evaluate("""() => {
            const gl = document.createElement('canvas').getContext('webgl');
            const dbg = gl ? gl.getExtension('WEBGL_debug_renderer_info') : null;
            return {
                userAgent: navigator.userAgent,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                language: navigator.language,
                languages: navigator.languages,
                hardwareConcurrency: navigator.hardwareConcurrency,
                platform: navigator.platform,
                oscpu: navigator.oscpu,
                outerWidth: window.outerWidth,
                outerHeight: window.outerHeight,
                innerWidth: window.innerWidth,
                innerHeight: window.innerHeight,
                screenX: window.screenX,
                screenY: window.screenY,
                historyLength: window.history.length,
                screenW: screen.width,
                screenH: screen.height,
                availH: screen.availHeight,
                colorDepth: screen.colorDepth,
                devicePixelRatio: window.devicePixelRatio,
                webglVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'null',
                webglRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'null',
            };
        }""")
        print(f"[+] Self: UA={probe['userAgent']!r} TZ={probe['timezone']} WebGL={probe['webglVendor']} / {probe['webglRenderer']}")
        print(f"[+] Self: outer={probe['outerWidth']}x{probe['outerHeight']} inner={probe['innerWidth']}x{probe['innerHeight']} screenXY=({probe['screenX']},{probe['screenY']}) histLen={probe['historyLength']} DPR={probe['devicePixelRatio']}")

        # Draw the SAME canvas TWICE in the SAME page to check if the browser
        # itself returns stable toDataURL on back-to-back draws.
        hashes = page.evaluate("""() => {
            const out = [];
            for (let i = 0; i < 3; i++) {
                const c = document.createElement('canvas'); c.width=240; c.height=60;
                const g = c.getContext('2d');
                g.textBaseline='top'; g.font='14px Arial';
                g.fillStyle='#f60'; g.fillRect(125,1,62,20);
                g.fillStyle='#069'; g.fillText('Trang·was·here·☠', 2, 15);
                g.fillStyle='rgba(102, 204, 0, 0.7)';
                g.fillText('Trang·was·here·☠', 4, 17);
                out.push(c.toDataURL());
            }
            return out;
        }""")
        same_page_hashes = [hashlib.sha256(h.encode()).hexdigest()[:16] for h in hashes]
        print(f"[+] Same-page 3x draws: {same_page_hashes}  {'STABLE' if len(set(same_page_hashes))==1 else 'DRIFTING'}")

        # Now the cross-launch probe — same canvas as spike_04 comparison
        own_data = page.evaluate("""() => {
            const c = document.createElement('canvas'); c.width=240; c.height=60;
            const g = c.getContext('2d');
            g.textBaseline='top'; g.font='14px Arial';
            g.fillStyle='#f60'; g.fillRect(125,1,62,20);
            g.fillStyle='#069'; g.fillText('Trang·was·here·☠', 2, 15);
            g.fillStyle='rgba(102, 204, 0, 0.7)';
            g.fillText('Trang·was·here·☠', 4, 17);
            return c.toDataURL();
        }""")
        own_hash_sha = hashlib.sha256(own_data.encode()).hexdigest()[:16]
        print(f"[+] Own canvas toDataURL hash: {own_hash_sha}")

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
        print(f"[+] WebGL Supported: {webgl_info.get('This browser supports WebGL','?')}")

        OUT_DIR.joinpath(f"{tag}_v6.json").write_text(json.dumps({
            "ip": ip, "canvas": canvas, "webgl": webgl_info, "self": probe, "own_hash": own_hash_sha,
            "same_page_hashes": same_page_hashes,
        }, indent=2))


if __name__ == "__main__":
    fp, seeds, webgl, fonts, voices, misc = load_or_create_identity()
    print(f"[i] FF version override: {FF_VERSION}")
    print(f"[i] Timezone override:   {TZ_OVERRIDE}")
    print(f"[i] Locked WebGL:        {webgl.get('webGl:vendor')} / {webgl.get('webGl:renderer')}")
    print(f"[i] Locked fonts:        {len(fonts)} families")
    print(f"[i] Locked voices:       {len(voices)} entries")
    print(f"[i] Locked window.history.length: {misc.get('window.history.length')}")

    run(1, "run1_v6", fp, seeds, webgl, fonts, voices, misc)
    run(1, "run2_v6", fp, seeds, webgl, fonts, voices, misc)
    run(2, "run3_v6", fp, seeds, webgl, fonts, voices, misc)

    print("\n=== CANVAS SIGNATURE COMPARISON (version 6) ===")
    sigs, own = {}, {}
    for tag in ["run1_v6", "run2_v6", "run3_v6"]:
        d = json.loads(OUT_DIR.joinpath(f"{tag}_v6.json").read_text())
        sigs[tag] = d["canvas"].get("Signature")
        own[tag]  = d["own_hash"]
    for k, v in sigs.items():
        print(f"  browserleaks {k}: {v}   | own canvas sha: {own[k]}")
    if len(set(sigs.values())) == 1 and len(set(own.values())) == 1:
        print("  ✅ Canvas signature STABLE across 3 runs — fingerprint persistence fixed!")
    else:
        print("  ⚠️ Canvas still drifting — see drift above")
