from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import pytest
from phantom import db
from phantom.services.session_service import SessionService
from phantom.services.lease_service import LeaseService, LeaseError

class NoProcess(SessionService):
    def _launch(self,sid,profile_id): return
class Clock:
    def __init__(self): self.now=datetime(2026,1,1,tzinfo=timezone.utc)
    def __call__(self): return self.now

@pytest.fixture
def svc(tmp_path:Path):
    os.environ['PHANTOM_DATA_DIR']=str(tmp_path); db.init_db()
    from phantom.services.profile_service import create_profile
    profile=create_profile('lease','custom','',0)
    sessions=NoProcess(); session,_=sessions.start_instant(profile['id'])
    clock=Clock(); leases=LeaseService(sessions,clock=clock,default_ttl=10)
    yield sessions,leases,clock,session
    os.environ.pop('PHANTOM_DATA_DIR',None)

def test_lease_owner_generation_monotonic_expiry(svc):
    sessions,leases,clock,session=svc; sid=session['id']
    one=leases.acquire(sid,ttl_seconds=10)
    with db.get_conn() as c:
        assert one['owner_token'] not in c.execute('SELECT owner_token_hash FROM session_leases').fetchone()[0]
    with pytest.raises(LeaseError): leases.heartbeat(sid,'wrong',one['generation'])
    clock.now+=timedelta(seconds=5)
    beat=leases.heartbeat(sid,one['owner_token'],one['generation'],ttl_seconds=10)
    assert beat['lease_expires_at']>one['lease_expires_at']
    clock.now+=timedelta(seconds=11)
    assert leases.expire_due()==[sid]
    assert sessions.get(sid)['status']=='stopped'
    events=sessions.events_after(sid)
    assert any(e['type']=='lease.expired' for e in events)
    with pytest.raises(LeaseError): leases.acquire(sid,ttl_seconds=10)

def test_release_is_owner_guarded_and_idempotent_absence(svc):
    _,leases,_,session=svc; lease=leases.acquire(session['id'])
    with pytest.raises(LeaseError): leases.release(session['id'],'wrong',lease['generation'])
    assert leases.release(session['id'],lease['owner_token'],lease['generation']) is True
    assert leases.release(session['id'],lease['owner_token'],lease['generation']) is False
