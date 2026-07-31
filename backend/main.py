"""FastAPI entry point for the Hermes Ollama backend.

Run with: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Assembly (HOS-066B). This module used to hand-list the routers it mounted, and
that list had fallen 19 routers behind the code: every Hermes OS endpoint
answered 404 while its router sat complete and tested in the tree. It now asks
:class:`~backend.core.bootstrap.HermesBootstrap` for the subsystems and mounts
whatever they own, so a new subsystem reaches the API by appearing in the
service catalogue rather than by someone remembering to edit this file.

Two router families remain distinct on purpose:

* the **legacy Hermes API** (``/chat``, ``/memory``, ``/tasks``, ...) keeps its
  unprefixed paths, because the existing frontend and the MCP tools call them
  there and nothing is gained by moving them;
* the **Hermes OS API** is mounted under the single canonical ``/api/v1``
  namespace, with ``/api/hermes-os/*`` kept as a redirect for clients written
  against HOS-003.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from backend.core.bootstrap import HermesBootstrap
from backend.core.bootstrap.router_registry import (
    API_V1,
    LEGACY_SDS_PREFIX,
    add_legacy_redirects,
    mount_all,
    rebase_router,
    mount_legacy_under_api,
)
from backend.core.config import get_settings
from backend.core.event_hub import get_event_hub
from backend.core.message_bus import get_message_bus
from backend.mcp_server.server import create_mcp_server
from backend.sds.routes import SDS_ROUTER

logger = logging.getLogger("hermes_os.main")

#: The legacy Hermes routers, which keep their own unprefixed paths.
_LEGACY_ROUTERS = (
    chat, system, security, files, memory, tasks, research, verify, write,
    vision, classify, messages, workflows, projects, skills, documents, git,
    snapshots, logs, ws, verification, evolution,
)


def create_app() -> FastAPI:
    """Builds a fresh app, a fresh bootstrap, and a fresh MCP server.

    Everything is per-app rather than process-global because the test suite
    calls this repeatedly in one interpreter: a shared MCP session manager can
    only be ``run()`` once (see ``create_mcp_server()``), and a shared container
    would leak one test's subsystem state into the next.
    """
    mcp_server = create_mcp_server()
    mcp_asgi_app = mcp_server.streamable_http_app()

    # ── STEP 1: composition root ──
    # Built before the lifespan so the routers exist at mount time; the
    # subsystems themselves are pure objects and need no running loop.
    bootstrap = HermesBootstrap()
    report = bootstrap.build()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """STEP 2 — unified startup and shutdown.

        Startup: configuration, event bus, event forwarding, legacy proxy,
        runtime registry, subsystem health verification, MCP session manager.
        Shutdown runs the inverse, and every step is independent so one failure
        cannot strand the others.
        """
        from backend.ral.event_bus import TopicPattern
        from backend.sds.runtime import (
            get_holder,
            get_runtime_registry,
            init_eventbus_in_holder,
            init_runtime_registry_in_holder,
            shutdown_runtime_registry,
        )

        # --- Configuration (fail fast) ---
        get_settings()

        # --- EventBusImpl (D-003) ---
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

        # --- Runtime registry and factory (HOS-008) ---
        # "stub" until now: /api/v1/runtimes reported a fake echo runtime as
        # active while 100% of real inference (chat, agents, missions) went
        # through Ollama directly via a separate code path that never
        # touched this registry. This makes the reported status match
        # reality; it does not yet route real inference through this
        # registry/RuntimeOrchestrator — that remains a separate, larger
        # rewiring (see the item flagged as such in CHANGELOG.md).
        runtime_holder = await init_runtime_registry_in_holder(default_runtime="ollama")
        _app.state.runtime_holder = runtime_holder
        _app.state.runtime_registry = get_runtime_registry()

        # --- Runtime catalogues (R-002 P2) ---
        # The composition root seeds the agent, tool and MCP registries while it
        # builds, but the runtime registry is only populated here, so it was
        # still empty when the assignment coordinator was told about it.
        bootstrap.seed_runtime_registries()

        # --- Route ownership ---
        # Route modules bind through a module-level global, so the app that is
        # running must reassert its bindings: in a process that built more than
        # one app (every test run) the last one built would otherwise be the one
        # answering HTTP calls.
        bootstrap.rebind_routes()

        # --- Subsystem health verification (STEP 9 / STEP 10) ---
        health = bootstrap.health()
        if health["status"] != "healthy":
            logger.warning(
                "startup health check: %s (unhealthy: %s)",
                health["status"],
                ", ".join(health["unhealthy"]),
            )
        logger.info(
            "Hermes OS ready: %d/%d subsystems, %d routers, %d endpoints",
            len(report.built),
            report.total_expected,
            report.routers_mounted,
            len(_app.routes),
        )

        async with AsyncExitStack() as stack:
            await stack.enter_async_context(mcp_server.session_manager.run())
            try:
                yield
            finally:
                # Inverse order of startup.
                # 1. Subsystems: flush pending state, stop schedulers.
                try:
                    bootstrap.shutdown()
                except Exception:
                    logger.warning("subsystem shutdown failed", exc_info=True)
                # 2. Runtimes (HOS-008).
                try:
                    await shutdown_runtime_registry()
                except Exception:
                    logger.warning("Runtime registry shutdown failed", exc_info=True)
                try:
                    await runtime_holder.stop()
                except Exception:
                    logger.warning("Runtime stop failed", exc_info=True)
                # 3. Legacy proxy.
                legacy_unsub()
                # 4. Wildcard forwarder.
                try:
                    get_holder().bus.unsubscribe(forward_sub)
                except Exception:
                    logger.warning("forward wildcard unsub failed", exc_info=True)
                # 5. EventBus last: everything above may still publish.
                try:
                    await holder.stop()
                except Exception:
                    logger.warning("EventBus stop failed", exc_info=True)

    app = FastAPI(title="Hermes OS", version="1.0.0-rc1", lifespan=lifespan)
    app.state.bootstrap = bootstrap
    app.state.container = bootstrap.container

    # Cockpit origins. This was hard-coded to http://localhost:3000, so a
    # Cockpit served from any other port — which happens the moment 3000 is
    # taken — got `OPTIONS ... 400 Bad Request` on every preflight and could not
    # reach the backend at all. HERMES_CORS_ORIGINS (comma-separated) overrides
    # the defaults; "*" allows any origin, which is for local development only.
    _origins_env = os.environ.get("HERMES_CORS_ORIGINS", "").strip()
    if _origins_env == "*":
        _cors_kwargs: dict[str, Any] = {"allow_origin_regex": ".*"}
    else:
        _origins = ([o.strip() for o in _origins_env.split(",") if o.strip()]
                    or ["http://localhost:3000", "http://127.0.0.1:3000",
                        "http://localhost:3010", "http://127.0.0.1:3010"])
        _cors_kwargs = {"allow_origins": _origins}

    app.add_middleware(
        CORSMiddleware,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Hermes-Model", "X-Hermes-Tier", "X-Hermes-Role"],
        **_cors_kwargs,
    )

    # ── Legacy Hermes API (unprefixed) ──
    # deprecated=True marks every route from these 21 modules in the OpenAPI
    # schema (Swagger UI shows them struck through) without changing behavior
    # at all — the first, purely-informational step of the deprecation cycle
    # docs/architecture/API_NAMESPACE_CONSISTENCY.md calls for. The same
    # routers republished under /api/v1 below (mount_legacy_under_api) are
    # the current, canonical way to reach these handlers and are deliberately
    # left undeprecated.
    for module in _LEGACY_ROUTERS:
        app.include_router(module.router, deprecated=True)

    # ── STEP 3 + 4: every subsystem router, one canonical namespace ──
    # SDS is rebased off its baked-in /api/hermes-os prefix rather than
    # duplicated, so there is still one implementation of each handler.
    mount_report = mount_all(
        app,
        [rebase_router(SDS_ROUTER, LEGACY_SDS_PREFIX), *bootstrap.routers],
        prefix=API_V1,
    )
    add_legacy_redirects(app, legacy=LEGACY_SDS_PREFIX, canonical=API_V1)
    app.state.mount_report = mount_report

    # ── P-002 : une seule base d'API pour le Cockpit ──
    # Les routeurs historiques ci-dessus sont aussi servis sous /api/v1, en
    # réutilisant les mêmes callables. Le client du Cockpit ne connaît que cette
    # base ; sans cela, la moitié Hermes-Ollama du produit lui reste inaccessible.
    app.state.legacy_migration = mount_legacy_under_api(app, _LEGACY_ROUTERS)

    app.mount("/mcp", mcp_asgi_app)

    # ── Client-input errors must not surface as 5xx ──
    #
    # 21 endpoints answered 500 to a malformed or incomplete body. The cause was
    # uniform: handlers that take a raw ``dict = Body(...)`` read required fields
    # with ``payload["field"]`` (KeyError) or coerce them into an enum
    # (ValueError). Both are the client's mistake, so 422 is the correct answer
    # and 500 is a lie that also hides a real failure behind indistinguishable
    # noise.
    #
    # Mapping the two exception types at the boundary fixes every affected
    # endpoint at once, without touching a single handler signature — which
    # matters this close to a release. The trade-off is that a ValueError or
    # KeyError raised by genuine server-side logic is now reported as 422 rather
    # than 500; the full traceback is logged at WARNING either way, so nothing is
    # actually hidden. Per-endpoint Pydantic request models remain the proper
    # fix and stay tracked as M-1 in ROADMAP Phase 9.

    @app.exception_handler(KeyError)
    async def _missing_field(request, exc: KeyError) -> JSONResponse:
        field = exc.args[0] if exc.args else "?"
        logger.warning(
            "missing field %r in request to %s %s", field,
            request.method, request.url.path, exc_info=exc,
        )
        return JSONResponse(
            status_code=422,
            content={"detail": [{
                "type": "missing",
                "loc": ["body", str(field)],
                "msg": f"Field required: {field!r}",
            }]},
        )

    @app.exception_handler(ValueError)
    async def _invalid_value(request, exc: ValueError) -> JSONResponse:
        logger.warning(
            "invalid value in request to %s %s", request.method, request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=422,
            content={"detail": [{
                "type": "value_error",
                "loc": ["body"],
                "msg": str(exc),
            }]},
        )

    # ── Assembly introspection (STEP 8 / 9 / 10) ──

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get(f"{API_V1}/system/assembly", tags=["system"])
    async def assembly_report() -> dict:
        """What the composition root built, and whether it is complete."""
        return {
            "bootstrap": report.to_dict(),
            "routers": mount_report.to_dict(),
        }

    @app.get(f"{API_V1}/system/dependencies", tags=["system"])
    async def dependency_report() -> dict:
        """Dependency graph of every subsystem (STEP 8)."""
        return bootstrap.dependency_report()

    # health() and statistics() walk every registered service and call
    # whichever zero-arg accessor each one exposes (ServiceHealthProbe,
    # health.py). One of those — the resource manager's GPU reading — makes a
    # blocking network call on a cold cache. Called directly, that blocked
    # this server's single event loop long enough to cascade into
    # httpx.ReadTimeout on unrelated, otherwise-instant routes queued behind
    # it (root-caused via backend/tests/test_smoke_live_server.py). Running
    # the whole synchronous call chain in a thread — rather than reworking
    # every service's accessor to be async — keeps the fix at the API
    # boundary, where it protects against any future accessor that blocks,
    # not just the one caught here.
    @app.get(f"{API_V1}/system/health", tags=["system"])
    async def subsystem_health() -> dict:
        return await asyncio.to_thread(bootstrap.health)

    @app.get(f"{API_V1}/system/ready", tags=["system"])
    async def subsystem_ready() -> dict:
        return bootstrap.ready()

    @app.get(f"{API_V1}/system/statistics", tags=["system"])
    async def subsystem_statistics() -> dict:
        return await asyncio.to_thread(bootstrap.statistics)

    return app


app = create_app()
