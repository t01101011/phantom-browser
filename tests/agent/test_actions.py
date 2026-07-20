import os
from pathlib import Path
import pytest

from phantom import db
from phantom.agent.actions import ActionController, ActionError


class FakePage:
    def __init__(self):
        self.url = "about:blank"; self.title_text = "Blank"; self.calls = []; self.events = {}
        self.elements = [{"backend_id":"button-1","role":"button","name":"Go","visible":True}]
    def on(self, event, callback): self.events.setdefault(event, []).append(callback)
    def goto(self, url, **kwargs): self.url=url; self.calls.append(("navigate",url))
    def title(self): return self.title_text
    def phantom_elements(self): return self.elements
    def phantom_action(self, backend_id, action, **kwargs): self.calls.append((action,backend_id,kwargs)); return {"ok":True}
    def keyboard_press(self, key): self.calls.append(("press",key))
    def scroll(self, dx, dy): self.calls.append(("scroll",dx,dy))
    def screenshot(self, **kwargs): return b"png"


def test_actions_stale_refs_humanized_seed_and_watchdogs():
    page=FakePage(); events=[]; ctl=ActionController(page,event_sink=lambda t,d: events.append((t,d)),seed=7,sleep=lambda _:None)
    snap=ctl.snapshot(); gen=snap["generation"]
    assert ctl.click("e1",gen)=={"ok":True}
    typed=ctl.type("e1",gen,"abc",humanized=True)
    assert typed["timing_ms"] == ActionController(page,seed=7,sleep=lambda _:None).timing("abc")
    ctl.snapshot()
    with pytest.raises(ActionError,match="stale") as err: ctl.click("e1",gen)
    assert err.value.code=="STALE_REF"
    page.events["popup"][0](type("P",(),{"url":"https://popup"})())
    page.events["download"][0](type("D",(),{"suggested_filename":"x.pdf"})())
    page.events["crash"][0]()
    assert [x[0] for x in events] == ["page.popup","page.download","page.crash"]


def test_controller_all_actions_and_validation():
    page=FakePage(); ctl=ActionController(page,seed=1,sleep=lambda _:None)
    assert ctl.navigate("https://example.test")["url"] == "https://example.test"
    snap=ctl.snapshot(); g=snap["generation"]
    ctl.press("Enter"); ctl.scroll(2,3); ctl.select("e1",g,"one")
    assert ctl.screenshot()==b"png"
    with pytest.raises(ActionError) as err: ctl.navigate("file:///etc/passwd")
    assert err.value.code=="INVALID_URL"


def test_session_action_service_enforces_status_and_lease(tmp_path: Path):
    os.environ["PHANTOM_DATA_DIR"]=str(tmp_path); db.init_db()
    from phantom.services.profile_service import create_profile
    from phantom.services.session_service import SessionService
    from phantom.services.lease_service import LeaseService
    class NoProcess(SessionService):
        def _launch(self,sid,profile_id): return
    sessions=NoProcess(); p=create_profile("action","custom","",0); session,_=sessions.start_instant(p["id"])
    leases=LeaseService(sessions); lease=leases.acquire(session["id"])
    from phantom.agent.actions import SessionActionService
    svc=SessionActionService(sessions,leases,page_provider=lambda _:FakePage())
    assert svc.perform(session["id"],"snapshot",{},lease["owner_token"],lease["generation"])["generation"]==1
    with pytest.raises(ActionError) as err: svc.perform(session["id"],"snapshot",{},"wrong",lease["generation"])
    assert err.value.code=="LEASE_MISMATCH"
    sessions.stop(session["id"])
    with pytest.raises(ActionError) as err: svc.perform(session["id"],"snapshot",{},lease["owner_token"],lease["generation"])
    assert err.value.code=="SESSION_NOT_READY"
    os.environ.pop("PHANTOM_DATA_DIR",None)
