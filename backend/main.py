"""FastAPI entry point for the Hermes Ollama backend.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import chat, files, memory, security, system, tasks
from backend.core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail fast and loud on a broken .env instead of surfacing a confusing
    500 the first time a request happens to touch Settings. Letting the
    ValidationError propagate (rather than catching it) is deliberate:
    uvicorn already prints it clearly as a startup failure, with the exact
    field and reason, and without the noisy nested-generator traceback a
    manual sys.exit() produces here."""
    get_settings()
    yield


app = FastAPI(title="Hermes Ollama", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Hermes-Model", "X-Hermes-Tier", "X-Hermes-Role"],
)

app.include_router(chat.router)
app.include_router(system.router)
app.include_router(security.router)
app.include_router(files.router)
app.include_router(memory.router)
app.include_router(tasks.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
