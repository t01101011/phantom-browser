import json
from pathlib import Path
from phantom.stealth import evaluate
P=Path(__file__).parent/"fixtures/good.json"
def load(): return json.loads(P.read_text())
def test_unsupported_webgpu_is_explicit():
    v=evaluate(load()); assert any(c["name"]=="run_0.webgpu" and c["status"]=="unsupported" for c in v["checks"])
def test_gpu_adapter_incoherence_fails():
    r=load(); r["runs"][0]["gpu"]["webgpu"]={"status":"pass","adapter_class":"discrete"}
    assert evaluate(r)["status"]=="fail"
def test_viewport_cannot_exceed_screen():
    r=load(); r["runs"][0]["screen"]["viewport_width"]=3000
    assert evaluate(r)["status"]=="fail"
