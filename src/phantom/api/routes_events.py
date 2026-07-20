"""SSE stream backed by the durable session event log."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from phantom.api.auth import verify_token_dep
from phantom.services.session_service import SessionNotFound

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token_dep)])


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request,
                         last_event_id: str | None = Header(None, alias="Last-Event-ID")):
    try:
        cursor = max(0, int(last_event_id or 0))
    except ValueError:
        raise HTTPException(400, "Last-Event-ID must be an integer")
    service = request.app.state.session_service
    try:
        service.get(session_id)
    except SessionNotFound:
        raise HTTPException(404, "session not found")

    async def generate():
        nonlocal cursor
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            events = service.events_after(session_id, cursor)
            if events:
                idle = 0
                for event in events:
                    cursor = event["sequence"]
                    payload = json.dumps(event["data"], separators=(",", ":"), default=str)
                    yield f"id: {cursor}\nevent: {event['type']}\ndata: {payload}\n\n"
            else:
                idle += 1
                if idle % 15 == 0:
                    yield ": keep-alive\n\n"
                if service.get(session_id)["status"] in {"stopped", "crashed"}:
                    return
                await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
