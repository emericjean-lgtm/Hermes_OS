"""FastAPI entry point for the Hermes Ollama backend.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import chat, system

app = FastAPI(title="Hermes Ollama", version="0.1.0")

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
