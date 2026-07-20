"""Controller-level agent actions (not a custom-engine CDP transport)."""
from __future__ import annotations
import random
import secrets
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from datetime import datetime, timezone
from phantom import db
from phantom.agent.snapshot import SnapshotIndex, SnapshotRefError
from phantom.agent.watchdogs import install_watchdogs


class ActionError(ValueError):
    def __init__(self, code: str, message: str): self.code=code; super().__init__(message)


class ActionController:
    def __init__(self, page: Any, *, event_sink: Callable[[str,dict],None] | None=None,
                 seed: int | str | None=None, sleep: Callable[[float],None]=time.sleep):
        self.page=page; self.index=SnapshotIndex(); self._rng=random.Random(seed); self._sleep=sleep
        install_watchdogs(page,event_sink or (lambda _t,_d:None))

    def timing(self,text: str)->list[int]: return [self._rng.randint(35,120) for _ in text]
    def navigate(self,url: str)->dict:
        parsed=urlsplit(url)
        if parsed.scheme not in {"http","https","about"}: raise ActionError("INVALID_URL","only http(s) and about URLs are allowed")
        self.page.goto(url,timeout=30000,wait_until="domcontentloaded")
        return {"url":self.page.url}
    def snapshot(self)->dict:
        elements=self.page.phantom_elements() if hasattr(self.page,"phantom_elements") else self._dom_elements()
        return self.index.build(self.page.url,self.page.title(),elements)
    def _dom_elements(self)->list[dict]:
        return self.page.locator("button,input,select,textarea,a[href],[role]").evaluate_all("""els => els.map((e,i)=>({backend_id:String(i),role:e.getAttribute('role')||({A:'link',BUTTON:'button',INPUT:'textbox',SELECT:'combobox',TEXTAREA:'textbox'}[e.tagName]||'generic'),name:e.getAttribute('aria-label')||e.innerText||e.getAttribute('placeholder')||'',value:e.value||'',visible:!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length)}))""")
    def _element(self,ref,generation):
        try: backend=self.index.resolve(ref,generation)
        except SnapshotRefError as exc: raise ActionError(exc.code,str(exc)) from exc
        if hasattr(self.page,"phantom_action"): return backend
        return self.page.locator("button,input,select,textarea,a[href],[role]").nth(int(backend))
    def click(self,ref,generation):
        el=self._element(ref,generation)
        if hasattr(self.page,"phantom_action"): return self.page.phantom_action(el,"click")
        el.click(); return {"ok":True}
    def type(self,ref,generation,text,humanized=True):
        el=self._element(ref,generation); delays=self.timing(text) if humanized else [0]*len(text)
        if hasattr(self.page,"phantom_action"): self.page.phantom_action(el,"type",text=text,timing_ms=delays)
        else:
            el.fill("")
            for char,delay in zip(text,delays): el.type(char); self._sleep(delay/1000)
        return {"ok":True,"timing_ms":delays,"humanized":humanized}
    def press(self,key):
        (self.page.keyboard_press(key) if hasattr(self.page,"keyboard_press") else self.page.keyboard.press(key)); return {"ok":True}
    def scroll(self,dx,dy):
        (self.page.scroll(dx,dy) if hasattr(self.page,"scroll") else self.page.mouse.wheel(dx,dy)); return {"ok":True}
    def select(self,ref,generation,value):
        el=self._element(ref,generation)
        if hasattr(self.page,"phantom_action"): return self.page.phantom_action(el,"select",value=value)
        el.select_option(value); return {"ok":True}
    def screenshot(self): return self.page.screenshot(full_page=True)


class SessionActionService:
    def __init__(self,sessions,leases,*,page_provider=None): self.sessions=sessions; self.leases=leases; self.page_provider=page_provider; self._controllers={}; self._generations={}
    def _authorize(self,sid,token,generation):
        session=self.sessions.get(sid)
        if session["status"] not in {"starting","ready"}: raise ActionError("SESSION_NOT_READY","session is not ready for actions")
        with db.get_conn() as c: row=c.execute("SELECT * FROM session_leases WHERE session_id=?",(sid,)).fetchone()
        if not row or datetime.fromisoformat(row["lease_expires_at"].replace("Z","+00:00")) <= datetime.now(timezone.utc) or int(row["generation"])!=generation or not secrets.compare_digest(row["owner_token_hash"],self.leases._hash(token)):
            raise ActionError("LEASE_MISMATCH","lease owner or generation mismatch")
    def perform(self,sid,action,args,token,generation):
        if self.leases.takeover_active(sid):
            raise ActionError("HUMAN_TAKEOVER_ACTIVE","agent input is paused during human takeover")
        self._authorize(sid,token,generation)
        if self.leases.snapshot_required(sid) and action != "snapshot":
            raise ActionError("FRESH_SNAPSHOT_REQUIRED","fresh snapshot required after ownership change")
        previous=self._generations.get(sid)
        if previous is not None and previous != generation and action != "snapshot":
            raise ActionError("FRESH_SNAPSHOT_REQUIRED","fresh snapshot required after ownership change")
        if self.page_provider is None:
            try: return self.sessions.request_action(sid,action,args)
            except Exception as exc: raise ActionError(getattr(exc,"code","ACTION_FAILED"),str(exc)) from exc
        if sid not in self._controllers:
            self._controllers[sid]=ActionController(self.page_provider(sid),event_sink=lambda t,d:self.sessions._event(sid,t,d),seed=sid)
        ctl=self._controllers[sid]
        allowed={"navigate","snapshot","click","type","press","scroll","select","screenshot"}
        if action not in allowed: raise ActionError("UNKNOWN_ACTION",f"unknown action {action!r}")
        result=getattr(ctl,action)(**args)
        if action == "snapshot":
            self._generations[sid]=generation
            self.leases.snapshot_refreshed(sid)
        return result
