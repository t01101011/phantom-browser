from __future__ import annotations
import os, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from phantom.api.app import create_app
from phantom.services.session_service import SessionService
from phantom.services.lease_service import LeaseService, ArtifactService
from phantom import db

class NoProcess(SessionService):
    def _launch(self, sid, profile_id): return

@pytest.fixture
def api(tmp_path: Path):
    data=tmp_path/'data'; (data/'runtime').mkdir(parents=True)
    token=secrets.token_urlsafe(20); (data/'runtime'/'.api_token').write_text(token)
    os.environ['PHANTOM_DATA_DIR']=str(data)
    app=create_app(); app.state.session_service=NoProcess(max_concurrency=1)
    app.state.lease_service=LeaseService(app.state.session_service)
    app.state.artifact_service=ArtifactService(app.state.session_service, max_bytes=100)
    client=TestClient(app); headers={'Authorization':f'Bearer {token}'}
    profile=client.post('/v1/profiles',headers=headers,json={'name':'instant'}).json()
    yield client,headers,profile,data,app
    os.environ.pop('PHANTOM_DATA_DIR',None)

def test_instant_idempotency_temp_cleanup_and_fifo(api):
    c,h,p,data,app=api
    r=c.post('/v1/sessions/instant',headers={**h,'Idempotency-Key':'i1'},json={'profile_id':p['id'],'ttl_seconds':60})
    assert r.status_code==201 and r.json()['session']['mode']=='instant'
    sid=r.json()['session']['id']; temp=data/'runtime'/'instant'/sid
    assert temp.is_dir() and r.json()['lease']['owner_token']
    replay=c.post('/v1/sessions/instant',headers={**h,'Idempotency-Key':'i1'},json={'profile_id':p['id']})
    assert replay.status_code==200 and replay.json()['session']['id']==sid and replay.json()['lease'] is None
    p2=c.post('/v1/profiles',headers=h,json={'name':'second'}).json()
    queued=c.post('/v1/sessions/instant',headers=h,json={'profile_id':p2['id']}).json()['session']
    assert queued['status']=='queued'
    assert c.delete(f'/v1/sessions/{sid}',headers=h).status_code==202
    assert not temp.exists()
    assert c.get(f"/v1/sessions/{queued['id']}",headers=h).json()['status']=='starting'

def test_artifacts_limits_redaction_and_traversal(api):
    c,h,p,data,app=api
    sid=c.post('/v1/sessions/instant',headers=h,json={'profile_id':p['id']}).json()['session']['id']
    raw=b'{"password":"very-secret","ok":1}'
    made=c.post(f'/v1/sessions/{sid}/artifacts/cookies',headers={**h,'Content-Type':'application/json'},content=raw)
    assert made.status_code==201 and made.json()['size_bytes']<100
    aid=made.json()['id']; got=c.get(f'/v1/artifacts/{aid}',headers=h)
    assert b'very-secret' not in got.content and b'*****' in got.content
    assert c.post(f'/v1/sessions/{sid}/artifacts/screenshot',headers={**h,'Content-Type':'text/plain'},content=b'x').status_code==422
    assert c.post(f'/v1/sessions/{sid}/artifacts/screenshot',headers={**h,'Content-Type':'image/png'},content=b'x'*101).status_code==422
    with db.get_conn() as conn:
        conn.execute("UPDATE artifacts SET path='../phantom.db' WHERE id=?",(aid,))
    assert c.get(f'/v1/artifacts/{aid}',headers=h).status_code==410
