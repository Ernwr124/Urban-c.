from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.database.connection import init_db
from app.routes import admin, auth, candidate, landing

app = FastAPI(title="HR Agent")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("HR_AGENT_SESSION_SECRET", "hr-agent-session"))

app.include_router(landing.router)
app.include_router(auth.router)
app.include_router(candidate.router)
app.include_router(admin.router)


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
