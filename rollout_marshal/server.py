"""The Cloud Run service.

Four endpoints, and only the first two matter:

    POST /tick/{app}     one decision. Cloud Scheduler calls this, every ten minutes.
    GET  /stream         server-sent events: the decision log, live. The demo's right pane.
    GET  /decisions/{app} the audit trail out of Firestore.
    GET  /healthz        for the Cloud Run health check.

The tick runs on a worker thread so a slow Play call cannot block the SSE stream that
is being filmed at the time.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from . import log
from .tick import Marshal

app = FastAPI(title="Rollout Marshal", version="0.1.0")
_marshal: Marshal | None = None


def marshal() -> Marshal:
    """Built on first use, so importing the module needs no credentials."""
    global _marshal
    if _marshal is None:
        _marshal = Marshal()
    return _marshal


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "brain": os.environ.get("MARSHAL_BRAIN", "scripted"),
        "store": os.environ.get("MARSHAL_STORE", "file"),
        "play": os.environ.get("MARSHAL_PLAY", "fixture"),
        "crash_feed": os.environ.get("MARSHAL_CRASH_FEED", "fixture"),
    }


@app.post("/tick/{app_id}")
async def tick(app_id: str) -> dict:
    try:
        return await asyncio.to_thread(marshal().tick, app_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.BUS.publish(log.ERROR, app_id, f"tick failed: {e}")
        raise HTTPException(status_code=500, detail=f"{e.__class__.__name__}: {e}")


@app.get("/decisions/{app_id}")
def decisions(app_id: str, limit: int = 50) -> dict:
    return {"app": app_id, "decisions": marshal().store.list_decisions(app_id, limit)}


@app.get("/log")
def recent_log(app_id: str | None = None, limit: int = 200) -> dict:
    return {"events": log.BUS.recent(app_id, limit)}


@app.get("/stream")
async def stream(app_id: str | None = None) -> StreamingResponse:
    q = log.BUS.subscribe()

    async def gen():
        try:
            while True:
                try:
                    event = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    continue
                if app_id and event["app"] != app_id:
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            log.BUS.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
