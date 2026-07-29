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
    documents,
    evolution,
    files,
    git,
    logs,
    memory,
    messages,
    projects,
    research,
    security,
    skills,
    snapshots,
    system,
    tasks,
    verification,
    verify,
    vision,
    workflows,
    write,
    ws,
)
from backend.tools.connectors.klaatcode.routes import klaatcode_router
from backend.core.config import get_settings
from backend.core.event_hub import EVENT_TYPES, get_event_hub
from backend.core.message_bus import get_message_bus
from backend.mcp_server.server import create_mcp_server
from backend.sds.dependencies import get_eventbus
from backend.sds.routes import SDS_ROUTER


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
        """HOS-003 lifespan: initialises EventBusImpl before ``yield``,
        forwards events to the legacy ``EventHub``, and preserves the
        ``MessageBus`` → ``agent.message`` → ``EventHub`` proxy.
        """
        import logging

        from backend.ral.event_bus import TopicPattern
        from backend.sds.runtime import get_holder, init_eventbus_in_holder

        logger = logging.getLogger("hermes_os.lifespan")

        # --- Pre-init (fail-fast) ---
        get_settings()

        # --- Initialiser EventBusImpl (D-003) ---
        eventbus_db = "./data/eventbus/eventbus.sqlite"
        holder = await init_eventbus_in_holder(eventbus_db)
        _app.state.eventbus_holder = holder

        # --- Forward EventBusImpl -> EventHub (D-002) ---
        ehub = get_event_hub()
        forward_sub = get_holder().bus.subscribe(
            TopicPattern("*"),
            lambda e: ehub.publish(e.topic.value, e.payload),
        )

        # --- Legacy proxy (D-001): MessageBus -> agent.message -> EventHub ---
        legacy_unsub = get_message_bus().subscribe(
            lambda message: ehub.publish("agent.message", message.to_dict())
        )

        # --- HOS-008: initialiser le RuntimeRegistry et le RuntimeFactory ---
        from backend.sds.runtime import (
            init_runtime_registry_in_holder,
            shutdown_runtime_registry,
        )

        runtime_holder = await init_runtime_registry_in_holder(default_runtime="stub")
        _app.state.runtime_holder = runtime_holder
        _app.state.runtime_registry = get_runtime_registry()
        logger.info("Runtime registry initialized")

        # --- MCP session manager (unchanged) ---
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(mcp_server.session_manager.run())
            try:
                yield
            finally:
                # Cleanup (inverse order of init)
                # 1. Stop all registered runtimes (HOS-008)
                try:
                    await shutdown_runtime_registry()
                except Exception:
                    logger.warning("Runtime registry shutdown failed", exc_info=True)
                # 2. Legacy runtime holder (kept for compatibility)
                try:
                    await runtime_holder.stop()
                except Exception:
                    logger.warning("Runtime stop failed", exc_info=True)
                # 2. Unsub legacy proxy
                legacy_unsub()
                # 3. Unsub wildcard forwarder
                try:
                    get_holder().bus.unsubscribe(forward_sub)
                except Exception:
                    logger.warning("forward wildcard unsub failed", exc_info=True)
                # 4. Stop EventBus last
                try:
                    await holder.stop()
                except Exception:
                    logger.warning("EventBus stop failed", exc_info=True)

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
    app.include_router(documents.router)
    app.include_router(git.router)
    app.include_router(snapshots.router)
    app.include_router(logs.router)
    app.include_router(ws.router)
    app.include_router(verification.router)
    app.include_router(evolution.router)
    app.include_router(klaatcode_router, prefix="/api/v1")
    app.mount("/mcp", mcp_asgi_app)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
