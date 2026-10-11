"""Authenticated single-process API with persistent request trajectories."""

import hmac
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException

from finagent.factory import create_engine
from finagent.schemas import ResearchRequest


def create_app(directory: Path | None = None, api_key: str | None = None) -> FastAPI:
    key = api_key or os.getenv("FINAGENT_API_KEY", "")
    if len(key) < 16 or not key.isascii():
        raise ValueError("FINAGENT_API_KEY must be an ASCII secret of at least 16 characters")
    root = directory or Path(os.getenv("FINAGENT_DIRECTORY", "runtime/api"))

    @asynccontextmanager
    async def lifespan(app):
        with create_engine(root) as engine:
            app.state.engine = engine
            yield

    app = FastAPI(title="FinAgent Research", version="1.0.0", lifespan=lifespan)

    def authenticate(x_api_key: str | None = Header(default=None)):
        if not x_api_key or not x_api_key.isascii() or not hmac.compare_digest(x_api_key, key):
            raise HTTPException(401, "Invalid API key")

    @app.get("/health")
    def health():
        return {"ready": True, "mode": "offline", "version": "1.0.0"}

    @app.post("/research", dependencies=[Depends(authenticate)])
    def research(request: ResearchRequest):
        thread = uuid.uuid4().hex
        return {"thread": thread, "report": app.state.engine.run(request, thread)}

    @app.get("/memory/{thread}", dependencies=[Depends(authenticate)])
    def memory(thread: str):
        try:
            result = app.state.engine.memory(thread)
        except ValueError as exc:
            raise HTTPException(422, "Invalid thread ID") from exc
        if not result["state"]:
            raise HTTPException(404, "Unknown thread")
        return result

    return app
