"""Hermes OS Mission Control API Router (HOS-028).

Aggregates all REST and WebSocket endpoints into a single :class:`MissionControlRouter`
that wraps a :class:`MissionControlService` instance.

Usage::

    service = MissionControlService(...)
    mcr = MissionControlRouter(service)
    app.include_router(mcr.router, prefix="/api/v1")
    app.include_router(mcr.ws_router)  # WebSocket at /ws/events
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.mission_control import MissionControlService

from . import hos_routes

logger = logging.getLogger(__name__)


class MissionControlRouter:
    """Aggregate all HOS-028 REST routes + WebSocket.

    Args:
        service: A fully configured :class:`MissionControlService` instance.
    """

    def __init__(self, service: MissionControlService) -> None:
        self._service = service

        # ── REST router (under /api/v1) ──
        self.router = APIRouter()

        # ── WebSocket router (unprefixed — WS paths are absolute) ──
        self.ws_router = APIRouter()

        self._register_routes()
        self._register_websocket()

    def _register_routes(self) -> None:
        """Attach all route functions to ``self.router``."""
        s = self._service

        # ── Mission routes ──
        self.router.add_api_route(
            "/missions", hos_routes.list_missions, methods=["GET"],
            summary="List all missions",
        )
        self.router.add_api_route(
            "/missions", hos_routes.create_mission, methods=["POST"],
            summary="Create and plan a mission",
        )
        self.router.add_api_route(
            "/missions/{mission_id}", hos_routes.get_mission, methods=["GET"],
            summary="Get mission details",
        )
        self.router.add_api_route(
            "/missions/{mission_id}/start", hos_routes.start_mission, methods=["POST"],
            summary="Start a mission",
        )
        self.router.add_api_route(
            "/missions/{mission_id}/pause", hos_routes.pause_mission, methods=["POST"],
            summary="Pause a mission",
        )
        self.router.add_api_route(
            "/missions/{mission_id}/resume", hos_routes.resume_mission, methods=["POST"],
            summary="Resume a mission",
        )
        self.router.add_api_route(
            "/missions/{mission_id}/cancel", hos_routes.cancel_mission, methods=["POST"],
            summary="Cancel a mission",
        )

        # ── Runtime routes ──
        self.router.add_api_route(
            "/runtimes", hos_routes.list_runtimes, methods=["GET"],
            summary="List all registered runtimes",
        )
        self.router.add_api_route(
            "/runtimes/health", hos_routes.runtime_health_summary, methods=["GET"],
            summary="Runtime health summary",
        )
        self.router.add_api_route(
            "/runtimes/metrics", hos_routes.runtime_metrics, methods=["GET"],
            summary="All runtime performance metrics",
        )
        self.router.add_api_route(
            "/runtimes/{name}", hos_routes.get_runtime, methods=["GET"],
            summary="Get single runtime info",
        )
        self.router.add_api_route(
            "/runtimes/{name}/health", hos_routes.get_runtime_health, methods=["GET"],
            summary="Get single runtime health",
        )
        self.router.add_api_route(
            "/runtimes/{name}/metrics", hos_routes.get_runtime_metrics, methods=["GET"],
            summary="Get single runtime metrics",
        )

        # ── Execution routes ──
        self.router.add_api_route(
            "/execution", hos_routes.get_execution_status, methods=["GET"],
            summary="Current execution status",
        )
        self.router.add_api_route(
            "/execution/start", hos_routes.start_execution, methods=["POST"],
            summary="Start mission execution",
        )
        self.router.add_api_route(
            "/execution/pause", hos_routes.pause_execution, methods=["POST"],
            summary="Pause execution",
        )
        self.router.add_api_route(
            "/execution/resume", hos_routes.resume_execution, methods=["POST"],
            summary="Resume execution",
        )
        self.router.add_api_route(
            "/execution/cancel", hos_routes.cancel_execution, methods=["POST"],
            summary="Cancel execution",
        )

        # ── Memory routes ──
        self.router.add_api_route(
            "/memory", hos_routes.list_memory_entries, methods=["GET"],
            summary="List memory entries",
        )
        # Static paths BEFORE parameterised paths to avoid route capture.
        self.router.add_api_route(
            "/memory/statistics", hos_routes.get_memory_statistics, methods=["GET"],
            summary="Memory statistics",
        )
        self.router.add_api_route(
            "/memory/search", hos_routes.search_memory_entries, methods=["GET"],
            summary="Search memory entries",
        )
        self.router.add_api_route(
            "/memory", hos_routes.store_memory, methods=["POST"],
            summary="Store a memory entry",
        )
        self.router.add_api_route(
            "/memory/{entry_id}", hos_routes.get_memory_entry, methods=["GET"],
            summary="Get memory entry",
        )
        self.router.add_api_route(
            "/memory/{entry_id}", hos_routes.update_memory_entry, methods=["PATCH"],
            summary="Update a memory entry",
        )

        # ── Skills routes ──
        self.router.add_api_route(
            "/skills", hos_routes.list_registered_skills, methods=["GET"],
            summary="List registered skills",
        )
        self.router.add_api_route(
            "/skills/select", hos_routes.select_skills, methods=["POST"],
            summary="Select skills by criteria",
        )
        self.router.add_api_route(
            "/skills/recommend", hos_routes.recommend_skills, methods=["POST"],
            summary="Recommend skills for a mission",
        )
        self.router.add_api_route(
            "/skills/bundles/{bundle_id}/load", hos_routes.load_skill_bundle, methods=["POST"],
            summary="Load a skill bundle",
        )
        self.router.add_api_route(
            "/skills/statistics", hos_routes.get_skill_statistics, methods=["GET"],
            summary="Skill orchestrator statistics",
        )

        # ── Events routes ──
        self.router.add_api_route(
            "/events", hos_routes.query_events, methods=["GET"],
            summary="Query system events",
        )
        self.router.add_api_route(
            "/events/statistics", hos_routes.get_event_statistics, methods=["GET"],
            summary="Event bus statistics",
        )
        self.router.add_api_route(
            "/events/export", hos_routes.export_events, methods=["GET"],
            summary="Export events as JSON",
        )
        self.router.add_api_route(
            "/events/publish", hos_routes.publish_event, methods=["POST"],
            summary="Publish a custom event",
        )
        self.router.add_api_route(
            "/events/clear", hos_routes.clear_events, methods=["POST"],
            summary="Clear event history",
        )

        # ── Hermes Agent integration routes ──
        self.router.add_api_route(
            "/hermes/status", hos_routes.hermes_status, methods=["GET"],
            summary="Hermes Agent status",
        )
        self.router.add_api_route(
            "/hermes/connect", hos_routes.hermes_connect, methods=["POST"],
            summary="Connect to Hermes Agent",
        )
        self.router.add_api_route(
            "/hermes/disconnect", hos_routes.hermes_disconnect, methods=["POST"],
            summary="Disconnect from Hermes Agent",
        )
        self.router.add_api_route(
            "/hermes/task", hos_routes.hermes_execute_task, methods=["POST"],
            summary="Execute a task via Hermes Agent",
        )
        self.router.add_api_route(
            "/hermes/sessions", hos_routes.hermes_list_sessions, methods=["GET"],
            summary="List Hermes Agent sessions",
        )

        # ── System routes ──
        self.router.add_api_route(
            "/health", hos_routes.health_check, methods=["GET"],
            summary="System health check",
        )
        self.router.add_api_route(
            "/status", hos_routes.system_status, methods=["GET"],
            summary="Overall system status",
        )
        self.router.add_api_route(
            "/diagnostics", hos_routes.system_diagnostics, methods=["GET"],
            summary="Full system diagnostics",
        )
        self.router.add_api_route(
            "/statistics", hos_routes.system_statistics, methods=["GET"],
            summary="Aggregated system statistics",
        )
        self.router.add_api_route(
            "/version", hos_routes.system_version, methods=["GET"],
            summary="System version",
        )
        self.router.add_api_route(
            "/tick", hos_routes.system_tick, methods=["POST"],
            summary="Advance all running missions by one step",
        )

        # ── Opérations (HOS-234) ──
        #
        # Ce que les jalons 5 à 16 ont produit, et que **rien n'exposait**
        # : registre des runs, lignée, contrat, points de reprise,
        # fournisseurs et leurs écarts, approbations et leurs portées,
        # version installée et santé.
        #
        # Toutes en `GET` seulement. Mission Control est une **vue** du
        # runtime, jamais un second runtime — une vue qui écrit devient
        # un second chemin vers l'état, et deux chemins vers l'état,
        # c'est la question « lequel fait foi ? » à chaque incident.
        for chemin, fonction, resume in (
            ("/operations", hos_routes.operations_apercu,
             "Vue d'ensemble des opérations"),
            ("/operations/missions/{mission}/runs", hos_routes.operations_runs,
             "Les tentatives d'une mission"),
            ("/operations/runs/{run}/lignee", hos_routes.operations_lignee,
             "La chaîne des tentatives, de la première à celle-ci"),
            ("/operations/runs/{run}/contrat", hos_routes.operations_contrat,
             "Ce qui devait être vrai à la fin"),
            ("/operations/checkpoints", hos_routes.operations_checkpoints,
             "Les points de reprise"),
            ("/operations/fournisseurs", hos_routes.operations_fournisseurs,
             "Fournisseurs cloud, écarts et disjoncteurs"),
            ("/operations/approbations", hos_routes.operations_approbations,
             "Approbations en attente et portées vivantes"),
            ("/operations/installation", hos_routes.operations_installation,
             "Version installée et auto-vérification"),
        ):
            self.router.add_api_route(chemin, fonction, methods=["GET"],
                                      summary=resume)

    def _register_websocket(self) -> None:
        """Register the WebSocket event stream endpoint."""

        @self.ws_router.websocket("/ws/events")
        async def event_stream(websocket: WebSocket) -> None:
            """Stream :class:`SystemEvent` objects from HOS-025 in real time.

            Each frame is a JSON object with ``id``, ``type``, ``source``,
            ``timestamp``, ``severity``, ``payload``, and ``correlation_id``.

            The client can filter by passing comma-separated source strings
            as a query parameter: ``/ws/events?sources=runtime,memory``.
            """
            await websocket.accept()
            bus = self._service._bus  # noqa: SLF001

            # The loop serving this connection. Events are published from
            # threadpool workers and background schedulers, which have no
            # running loop of their own, so it has to be captured here rather
            # than looked up at publish time.
            loop = asyncio.get_running_loop()

            # Parse optional source filter
            sources_raw = websocket.query_params.get("sources", "")
            source_filter: Optional[set[str]] = None
            if sources_raw:
                source_filter = set(s.strip() for s in sources_raw.split(",") if s.strip())

            # Register a callback that pushes events over the socket.
            async def send_event(event: Any) -> None:
                try:
                    payload = {
                        "id": event.id,
                        "type": event.type.value if hasattr(event.type, "value") else str(event.type),
                        "source": event.source,
                        "timestamp": event.timestamp,
                        "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity),
                        "payload": event.payload,
                        "correlation_id": event.correlation_id,
                    }
                    await websocket.send_json(payload)
                except Exception:
                    # A client that has gone away must not break the publisher;
                    # the disconnect is handled by the receive loop below.
                    logger.debug("WebSocket send failed", exc_info=True)

            def _handler(event: Any) -> None:
                """Called by the bus, possibly from a worker thread.

                ``get_event_loop()`` + ``ensure_future`` was wrong on both
                counts here: off the main thread the lookup raises (and was
                swallowed, so the event silently vanished), and ensure_future is
                not thread-safe even on the right thread.
                """
                if source_filter and event.source not in source_filter:
                    return
                if loop.is_closed():
                    return
                try:
                    if asyncio.get_running_loop() is loop:
                        loop.create_task(send_event(event))
                        return
                except RuntimeError:
                    pass  # no running loop in this thread — expected
                try:
                    asyncio.run_coroutine_threadsafe(send_event(event), loop)
                except RuntimeError:
                    logger.debug("could not schedule WebSocket send", exc_info=True)

            bus.subscribe(_handler)

            try:
                # Keep the connection alive until the client disconnects.
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                bus.unsubscribe(_handler)


class MissionControlAPI:
    """Convenience class that creates a :class:`MissionControlRouter`
    from a :class:`MissionControlService` instance.

    Usage::

        api = MissionControlAPI(service)
        app.include_router(api.router, prefix="/api/v1")
        app.include_router(api.ws_router)  # /ws/events
    """

    def __init__(self, service: MissionControlService) -> None:
        self._router = MissionControlRouter(service)

    @property
    def router(self) -> APIRouter:
        """The REST router (attach at ``/api/v1``)."""
        return self._router.router

    @property
    def ws_router(self) -> APIRouter:
        """The WebSocket router (attach at root)."""
        return self._router.ws_router
