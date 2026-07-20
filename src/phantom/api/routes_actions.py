"""Lease-guarded compact agent action endpoint."""
import base64
from typing import Any, Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from phantom.api.auth import verify_token_dep
from phantom.agent.actions import ActionError
from phantom.services.session_service import SessionNotFound

router=APIRouter(prefix="/v1/sessions",dependencies=[Depends(verify_token_dep)])
class ActionBody(BaseModel):
    action: Literal["navigate","snapshot","click","type","press","scroll","select","screenshot"]
    generation: int=Field(ge=1)
    ref: str|None=None; url: str|None=None; text: str|None=None; key: str|None=None; value: str|None=None
    dx: float=0; dy: float=0; humanized: bool=True

def lease_token(value: str|None=Header(None,alias="X-Lease-Token")):
    if not value: raise HTTPException(401,"missing lease token")
    return value

@router.post("/{session_id}/actions")
def action(session_id:str,body:ActionBody,request:Request,token:str=Depends(lease_token)):
    args:dict[str,Any]={}
    required={"navigate":("url",),"click":("ref",),"type":("ref","text"),"press":("key",),"select":("ref","value")}
    for name in required.get(body.action,()):
        val=getattr(body,name)
        if val is None: raise HTTPException(422,{"code":"INVALID_ARGUMENT","message":f"{name} is required"})
        args[name]=val
    if body.action in {"click","type","select"}: args["generation"]=body.generation
    if body.action=="type": args["humanized"]=body.humanized
    if body.action=="scroll": args={"dx":body.dx,"dy":body.dy}
    try:
        result=request.app.state.action_service.perform(session_id,body.action,args,token,body.generation)
        if isinstance(result,bytes): return {"mime":"image/png","bytes":base64.b64encode(result).decode("ascii")}
        return result
    except SessionNotFound: raise HTTPException(404,{"code":"SESSION_NOT_FOUND","message":"session not found"})
    except ActionError as exc: raise HTTPException(409,{"code":exc.code,"message":str(exc)})
