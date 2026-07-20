#!/usr/bin/env python3
"""Reproducible Chromium acceptance probe.

The probe intentionally records raw browser values rather than producing a stealth
score. It launches an explicit executable with an explicit persistent user-data-dir,
attaches and reconnects over CDP, then relaunches the same profile.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import platform
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SURFACE_KEYS = (
    "binary",
    "persistent_user_data_dir",
    "cdp_attach_reconnect",
    "ua_ua_ch",
    "worker_main",
    "webgl_webgpu",
    "fonts",
    "canvas_audio_client_rects",
    "webrtc_dns",
    "tls_http2",
)

PAGE = b"""<!doctype html><meta charset=utf-8><title>probe</title>
<style>#rect{font:17px Arial;width:max-content}</style><div id=rect>Phantom probe MmWw 0123456789</div>
<script>navigator.serviceWorker?.register('/sw.js')</script>"""
SW = b"self.addEventListener('fetch',()=>{});"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = SW if self.path == "/sw.js" else PAGE
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript" if self.path == "/sw.js" else "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def report_checksum(report: dict[str, Any]) -> str:
    clean = dict(report)
    clean.pop("checksum_sha256", None)
    return hashlib.sha256(canonical_json(clean)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def launch(executable: Path, user_data_dir: Path, extra_args: list[str]) -> tuple[subprocess.Popen, str]:
    active = user_data_dir / "DevToolsActivePort"
    active.unlink(missing_ok=True)
    command = [
        str(executable),
        f"--user-data-dir={user_data_dir}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--headless=new",
        "--no-sandbox",
        "about:blank",
        *extra_args,
    ]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if active.exists():
            port = active.read_text().splitlines()[0]
            return process, f"http://127.0.0.1:{port}"
        if process.poll() is not None:
            stderr = process.stderr
            error = stderr.read().decode(errors="replace")[-2000:] if stderr else ""
            raise RuntimeError(f"browser exited {process.returncode}: {error}")
        time.sleep(0.05)
    process.terminate()
    raise TimeoutError("DevToolsActivePort was not created")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def measure(page) -> dict[str, Any]:
    return page.evaluate("""async () => {
      const canvas = document.createElement('canvas'); canvas.width=240; canvas.height=60;
      const c = canvas.getContext('2d'); c.font='17px Arial'; c.fillStyle='#123456';
      c.fillText('Phantom probe MmWw 0123456789', 2, 25);
      const hash = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))).map(x=>x.toString(16).padStart(2,'0')).join('');
      const gl = document.createElement('canvas').getContext('webgl');
      const dbg = gl?.getExtension('WEBGL_debug_renderer_info');
      const worker = await new Promise(resolve => {
        const src = `postMessage({ua:navigator.userAgent,platform:navigator.platform,languages:navigator.languages,hardwareConcurrency:navigator.hardwareConcurrency})`;
        const w = new Worker(URL.createObjectURL(new Blob([src],{type:'text/javascript'})));
        w.onmessage=e=>resolve(e.data); w.onerror=e=>resolve({error:e.message});
      });
      let offer=[]; try {
        const pc=new RTCPeerConnection({iceServers:[]}); pc.createDataChannel('x');
        pc.onicecandidate=e=>{if(e.candidate) offer.push(e.candidate.candidate)};
        await pc.setLocalDescription(await pc.createOffer()); await new Promise(r=>setTimeout(r,300)); pc.close();
      } catch(e) { offer=[`error:${e.name}`] }
      const uaData=navigator.userAgentData;
      const hints=uaData ? await uaData.getHighEntropyValues(['architecture','bitness','model','platform','platformVersion','uaFullVersion','fullVersionList']) : null;
      return {
        ua_ua_ch:{userAgent:navigator.userAgent,platform:navigator.platform,brands:uaData?.brands||null,mobile:uaData?.mobile??null,hints},
        worker_main:{main:{ua:navigator.userAgent,platform:navigator.platform,languages:navigator.languages,hardwareConcurrency:navigator.hardwareConcurrency},dedicatedWorker:worker,serviceWorkerSupported:'serviceWorker' in navigator},
        webgl_webgpu:{webglVendor:dbg?gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL):null,webglRenderer:dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL):null,webgpuSupported:!!navigator.gpu},
        fonts:{check:['Arial','Times New Roman','Courier New','Segoe UI','Noto Sans'].map(font=>[font,document.fonts.check(`16px "${font}"`)]),arialWidth:c.measureText('Phantom probe MmWw 0123456789').width},
        canvas_audio_client_rects:{canvasSha256:await hash(canvas.toDataURL()),audioContext:{supported:!!(window.AudioContext||window.webkitAudioContext),sampleRate:(window.AudioContext||window.webkitAudioContext)?new (window.AudioContext||window.webkitAudioContext)().sampleRate:null},clientRects:Array.from(document.querySelector('#rect').getClientRects()).map(r=>({x:r.x,y:r.y,width:r.width,height:r.height}))},
        webrtc_dns:{iceCandidates:offer}
      }
    }""")


def run_probe(executable: Path, candidate: str, output: Path, user_data_dir: Path, extra_args: list[str]) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    executable = executable.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    process = None
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "candidate": candidate,
        "host": {"os": platform.system(), "arch": platform.machine()},
        "surfaces": {},
    }
    try:
        process, endpoint = launch(executable, user_data_dir, extra_args)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="networkidle")
            page.evaluate("localStorage.setItem('phantom_probe_persistent','v1')")
            measured = measure(page)
            version = browser.version
            browser.close()  # Disconnect; browser process remains alive.
            reconnected = playwright.chromium.connect_over_cdp(endpoint)
            # localStorage is origin-scoped, so revisit the fixture before reading it.
            reconnect_page = reconnected.contexts[0].new_page()
            reconnect_page.goto(url)
            reconnect_value = reconnect_page.evaluate("localStorage.getItem('phantom_probe_persistent')")
            cdp = reconnected.new_browser_cdp_session()
            cdp.send("Browser.close")
            process.wait(timeout=8)
        process = None
        process, endpoint2 = launch(executable, user_data_dir, extra_args)
        with sync_playwright() as playwright:
            relaunched = playwright.chromium.connect_over_cdp(endpoint2)
            page2 = relaunched.contexts[0].new_page(); page2.goto(url)
            relaunch_value = page2.evaluate("localStorage.getItem('phantom_probe_persistent')")
            relaunched.close()
        report["surfaces"] = {
            "binary": {"path": str(executable), "sha256": sha256_file(executable), "browserVersion": version},
            "persistent_user_data_dir": {"reconnectValue": reconnect_value, "relaunchValue": relaunch_value, "passed": reconnect_value == relaunch_value == "v1"},
            "cdp_attach_reconnect": {"endpointScheme": "http", "passed": reconnect_value == "v1"},
            **measured,
            "tls_http2": {"status": "not_measured", "reason": "requires controlled packet/server capture; browser JS cannot attest TLS fingerprint or HTTP/2 framing"},
        }
    finally:
        if process is not None:
            stop(process)
        server.shutdown(); server.server_close()
    missing = sorted(set(SURFACE_KEYS) - set(report["surfaces"]))
    if missing:
        raise RuntimeError(f"probe did not populate surfaces: {missing}")
    report["checksum_sha256"] = report_checksum(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--user-data-dir", type=Path)
    parser.add_argument("--extra-arg", action="append", default=[])
    args = parser.parse_args()
    temporary = None
    profile = args.user_data_dir
    if profile is None:
        temporary = tempfile.TemporaryDirectory(prefix="phantom-chromium-probe-")
        profile = Path(temporary.name)
    report = run_probe(args.executable, args.candidate, args.output, profile, args.extra_arg)
    print(json.dumps({"output": str(args.output), "checksum_sha256": report["checksum_sha256"]}))
    if temporary:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
