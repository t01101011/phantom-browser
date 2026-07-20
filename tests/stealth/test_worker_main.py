import copy
import json
from pathlib import Path
from phantom.stealth import evaluate

FIX=Path(__file__).parent/"fixtures"
def load(name="good.json"): return json.loads((FIX/name).read_text())

def test_all_worker_types_are_explicit_and_coherent():
    verdict=evaluate(load())
    names={x["name"]:x["status"] for x in verdict["checks"]}
    for run in range(2):
        assert names[f"run_{run}.worker_coherence"] == "pass"
        assert names[f"run_{run}.shared_worker_coherence"] == "pass"
        assert names[f"run_{run}.service_worker_coherence"] == "pass"

def test_missing_service_worker_is_failure_not_unsupported():
    report=load(); del report["runs"][0]["contexts"]["service_worker"]
    assert evaluate(report)["status"] == "fail"

def test_relaunch_drift_fails():
    assert evaluate(load("bad.json"))["status"] == "fail"
