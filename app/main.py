import asyncio
import json

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse

from .firebase_init import init_firebase
from .logbus import logbus, log
from .processor import processor

app = FastAPI(title="Attendor Worker")


@app.on_event("startup")
async def startup():
    try:
        init_firebase()
        log("info", "firebase admin initialized")
    except Exception as exc:
        log("error", f"firebase init failed: {exc}")
        raise
    processor.start()


@app.on_event("shutdown")
async def shutdown():
    processor.stop()


@app.get("/")
async def index():
    return FileResponse("app/static/logs.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/logs")
async def logs():
    return {"logs": logbus.snapshot()}


@app.get("/api/logs/stream")
async def logs_stream(request: Request):
    q = logbus.subscribe()

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            logbus.unsubscribe(q)

    return StreamingResponse(event_stream(), media_type="text/event-stream")