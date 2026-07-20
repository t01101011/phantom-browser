import json
from pathlib import Path
from phantom.stealth import evaluate
FIX=Path(__file__).parent/"fixtures"
def load(name): return json.loads((FIX/name).read_text())
def test_ua_ch_major_matches_ua():
    assert evaluate(load("good.json"))["status"] == "conditional_pass"
def test_ua_ch_drift_is_red():
    v=evaluate(load("bad.json")); assert any(c["name"]=="run_0.ua_ua_ch" and c["status"]=="fail" for c in v["checks"])
def test_unsupported_ua_ch_is_not_false_green():
    r=load("good.json"); r["runs"][0]["ua_ch"]={"status":"unsupported","reason":"Firefox surface"}; r["runs"][1]["ua_ch"]={"status":"unsupported","reason":"Firefox surface"}
    v=evaluate(r); assert v["status"]=="conditional_pass" and v["counts"]["unsupported"]>=1
