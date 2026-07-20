import os, secrets
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from phantom.api.app import create_app
from phantom.services.session_service import SessionService
from phantom.services.lease_service import LeaseService
from phantom.agent.actions import SessionActionService

class FakePage:
    def __init__(self):
        self.url="about:blank"; self.elements=[{"backend_id":"button-1","role":"button","name":"Go","visible":True}]; self.events={}
    def on(self,event,callback): self.events.setdefault(event,[]).append(callback)
    def goto(self,url,**kwargs): self.url=url
    def title(self): return "Blank"
    def phantom_elements(self): return self.elements
    def phantom_action(self,backend_id,action,**kwargs): return {"ok":True}
    def screenshot(self,**kwargs): return b"png"

class NoProcess(SessionService):
    def _launch(self,sid,profile_id): return

@pytest.fixture
def api(tmp_path:Path):
    data=tmp_path/"data"; (data/"runtime").mkdir(parents=True); token=secrets.token_urlsafe(20); (data/"runtime"/".api_token").write_text(token)
    os.environ["PHANTOM_DATA_DIR"]=str(data); app=create_app(); sessions=NoProcess(); leases=LeaseService(sessions)
    app.state.session_service=sessions; app.state.lease_service=leases; app.state.action_service=SessionActionService(sessions,leases,page_provider=lambda _:FakePage())
    client=TestClient(app); h={"Authorization":f"Bearer {token}"}; p=client.post("/v1/profiles",headers=h,json={"name":"a"}).json(); instant=client.post("/v1/sessions/instant",headers=h,json={"profile_id":p["id"]}).json(); s=instant["session"]; lease=instant["lease"]
    yield client,h,s,lease
    os.environ.pop("PHANTOM_DATA_DIR",None)

def test_action_api_auth_lease_compact_and_errors(api):
    c,h,s,l=api; sid=s["id"]; owner={**h,"X-Lease-Token":l["owner_token"]}
    assert c.post(f"/v1/sessions/{sid}/actions",json={"action":"snapshot","generation":l["generation"]}).status_code==403
    snap=c.post(f"/v1/sessions/{sid}/actions",headers=owner,json={"action":"snapshot","generation":l["generation"]})
    assert snap.status_code==200 and snap.json()["elements"][0]["ref"]=="e1"
    bad=c.post(f"/v1/sessions/{sid}/actions",headers={**h,"X-Lease-Token":"bad"},json={"action":"snapshot","generation":l["generation"]})
    assert bad.status_code==409 and bad.json()["detail"]["code"]=="LEASE_MISMATCH"
    stale=c.post(f"/v1/sessions/{sid}/actions",headers=owner,json={"action":"click","generation":snap.json()["generation"],"ref":"e1"})
    assert stale.status_code==200
    c.post(f"/v1/sessions/{sid}/actions",headers=owner,json={"action":"snapshot","generation":l["generation"]})
    stale=c.post(f"/v1/sessions/{sid}/actions",headers=owner,json={"action":"click","generation":snap.json()["generation"],"ref":"e1"})
    assert stale.status_code==409 and stale.json()["detail"]["code"]=="STALE_REF"
