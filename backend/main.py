"""FastAPI entry point for the Hermes Ollama backend.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    chat,
    classify,
    evolution,
    files,
    memory,
    messages,
    projects,
    research,
    security,
    skills,
    system,
    tasks,
    verify,
    vision,
    workflows,
    write,
)
from backend.core.config import get_settings
from backend.mcp_server.server import create_mcp_server


def create_app() -> FastAPI:
    """Builds a fresh app (and a fresh MCP server/session-manager to go
    with it — see create_mcp_server()'s docstring for why that has to be
    fresh per app rather than shared). `app` below is the module-level
    instance uvicorn actually serves; tests call this directly so each
    one gets its own isolated MCP session manager."""
    mcp_server = create_mcp_server()
    mcp_asgi_app = mcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Fail fast and loud on a broken .env instead of surfacing a
        confusing 500 the first time a request happens to touch Settings.
        Letting the ValidationError propagate (rather than catching it)
        is deliberate: uvicorn already prints it clearly as a startup
        failure, with the exact field and reason, and without the noisy
        nested-generator traceback a manual sys.exit() produces here.

        Also starts the MCP server's session manager: Starlette's Mount
        does not auto-run a mounted sub-app's own lifespan, so it has to
        be entered explicitly here for the streamable-HTTP transport at
        /mcp to work (see backend/mcp_server/server.py)."""
        get_settings()
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(mcp_server.session_manager.run())
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
    app.include_router(research.router)
    app.include_router(verify.router)
    app.include_router(write.router)
    app.include_router(vision.router)
    app.include_router(classify.router)
    app.include_router(messages.router)
    app.include_router(workflows.router)
    app.include_router(projects.router)
    app.include_router(skills.router)
    app.include_router(evolution.router)
    app.mount("/mcp", mcp_asgi_app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
