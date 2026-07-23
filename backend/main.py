"""FastAPI entry point for the Hermes Ollama backend.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from backend.api.routes import chat, system
from backend.core.config import get_settings

logger = logging.getLogger("hermes.startup")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail fast and loud on a broken .env instead of surfacing a confusing
    500 the first time a request happens to touch Settings."""
    try:
        get_settings()
    except ValidationError as exc:
        logger.error("Invalid configuration in .env:\n%s", exc)
        sys.exit(1)
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
