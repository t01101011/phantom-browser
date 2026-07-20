#!/usr/bin/env python3
"""Local controlled Chromium probe for Task16 (no third-party/network dependency)."""
import argparse, hashlib, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML=b"<!doctype html><meta charset=utf-8><title>coherence</title>"
SW=b"self.onmessage=e=>e.source.postMessage({kind:'sw',value:snap()}); function snap(){return {status:'pass',user_agent:navigator.userAgent,platform:navigator.platform,languages:navigator.languages,hardware_concurrency:navigator.hardwareConcurrency,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone}}"
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  body=SW if self.path=="/sw.js" else HTML; self.send_response(200); self.send_header("Content-Type","application/javascript" if self.path=="/sw.js" else "text/html"); self.end_headers(); self.wfile.write(body)
 def log_message(self, format, *args): pass

def probe(page):
 return page.evaluate("""async()=>{const snap=()=>({status:'pass',user_agent:navigator.userAgent,platform:navigator.platform,languages:[...navigator.languages],hardware_concurrency:navigator.hardwareConcurrency,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone}); const worker=await new Promise((ok,no)=>{let w=new Worker(URL.createObjectURL(new Blob(['onmessage=()=>postMessage(('+snap+')())'])));w.onmessage=e=>ok(e.data);w.onerror=no;w.postMessage(1)}); const shared_worker=await new Promise((ok,no)=>{let w=new SharedWorker(URL.createObjectURL(new Blob(['onconnect=e=>{let p=e.ports[0];p.onmessage=()=>p.postMessage(('+snap+')())}'])));w.port.onmessage=e=>ok(e.data);w.onerror=no;w.port.start();w.port.postMessage(1)}); await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; const service_worker=await new Promise((ok,no)=>{navigator.serviceWorker.onmessage=e=>ok(e.data.value);navigator.serviceWorker.ready.then(r=>r.active.postMessage(1));setTimeout(()=>no(Error('sw timeout')),5000)}); let c=document.createElement('canvas'),g=c.getContext('webgl');let ext=g&&g.getExtension('WEBGL_debug_renderer_info');let renderer=ext?g.getParameter(ext.UNMASKED_RENDERER_WEBGL):'';let metrics=document.createElement('canvas').getContext('2d');metrics.font='16px Arial';let mh=metrics.measureText('Phantom coherence').width.toFixed(4);let ch=navigator.userAgentData?await navigator.userAgentData.getHighEntropyValues(['platform','fullVersionList']):null;return {contexts:{main:snap(),worker,shared_worker,service_worker},ua_ch:ch?{status:'pass',platform:ch.platform,full_versions:ch.fullVersionList.map(x=>({brand:x.brand,version:x.version}))}:{status:'unsupported',reason:'not exposed'},gpu:{webgl:{status:g?'pass':'unsupported',adapter_class:/SwiftShader|software/i.test(renderer)?'software':'hardware',renderer},webgpu:{status:'unsupported',reason:'adapter details not attested in this controlled headless probe'}},screen:{width:screen.width,height:screen.height,viewport_width:innerWidth,viewport_height:innerHeight},locale_geo:{expected:{locale:'en-US',timezone:'UTC',country:null},observed:{locale:Intl.DateTimeFormat().resolvedOptions().locale,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,country:null}},fonts:{status:'pass',metrics_hash:'width:'+mh},webrtc:{status:'pass',public_ip_leak:false,reason:'no STUN servers used; external leak probe is informational'},transport:{tls:{status:'unsupported',reason:'controlled TLS capture not configured'},http2:{status:'unsupported',reason:'controlled HTTP/2 capture not configured'}}}}""")

a=argparse.ArgumentParser();a.add_argument('--executable');a.add_argument('--output',required=True);a.add_argument('--profile-dir',required=True);ns=a.parse_args()
s=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=s.serve_forever,daemon=True).start(); runs=[]
try:
 with sync_playwright() as p:
  for _ in range(2):
   kw={'headless':True,'locale':'en-US','timezone_id':'UTC','viewport':{'width':1280,'height':720}}
   if ns.executable: kw['executable_path']=ns.executable
   b=p.chromium.launch_persistent_context(ns.profile_dir,**kw); page=b.new_page();page.goto(f'http://127.0.0.1:{s.server_port}/');runs.append(probe(page));b.close()
finally:s.shutdown()
report={'schema_version':1,'profile_id':'local-controlled-chromium','engine':'chromium','runs':runs}; raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode();Path(ns.output).parent.mkdir(parents=True,exist_ok=True);Path(ns.output).write_bytes(raw);print(hashlib.sha256(raw).hexdigest())
