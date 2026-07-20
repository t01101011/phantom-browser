import json
from pathlib import Path
from phantom.stealth import evaluate, redact
P=Path(__file__).parent/"fixtures/good.json"
def load(): return json.loads(P.read_text())
def test_offline_expected_geo_gate():
    r=load(); r["runs"][0]["locale_geo"]["observed"]["timezone"]="Europe/Berlin"
    assert evaluate(r)["status"]=="fail"
def test_webrtc_public_ip_leak_fails():
    r=load(); r["runs"][0]["webrtc"]["public_ip_leak"]=True
    assert evaluate(r)["status"]=="fail"
def test_proxy_credentials_and_tokens_redacted():
    safe=redact({"proxy_url":"http://alice:hunter2@proxy.test:9","nested":{"token":"secret"}})
    raw=json.dumps(safe); assert "hunter2" not in raw and "secret" not in raw and raw.count("[REDACTED]")==2
