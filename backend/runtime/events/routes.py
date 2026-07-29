"""FastAPI routes for the Runtime Event Bus (HOS-034).

Provides REST endpoints and a WebSocket for real-time event streaming.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.runtime.events.event_bus import RuntimeEventBus
from backend.runtime.events.event_models import (
    RuntimeEventCreateRequest,
    RuntimeEventListResponse,
    RuntimeEventModel,
    RuntimeEventResponse,
    RuntimeEventSeverity,
)
from backend.runtime.events.event_store import EventStore

# ── Router ─────────────────────────────────────────────────

router = APIRouter(prefix="/runtime/events", tags=["runtime-events"])

# Module-level singleton references (set by create_runtime_event_routes)
_bus: Optional[RuntimeEventBus] = None
_store: Optional[EventStore] = None
_ws_clients: list[WebSocket] = []


def create_runtime_event_routes(
    bus: RuntimeEventBus,
    store: Optional[EventStore] = None,
) -> APIRouter:
    """Factory: bind a bus and optional store to the routes."""
    global _bus, _store
    _bus = bus
    _store = store

    # Auto-publish in-memory events to WebSocket clients
    _original_publish = bus.publish

    def _publish_and_broadcast(event: RuntimeEventModel) -> None:
        _original_publish(event)
        if _store:
            try:
                _store.store(event)
            except Exception:
                pass
        # Broadcast to WebSocket clients
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_broadcast(event))
        except RuntimeError:
            pass

    bus.publish = _publish_and_broadcast  # type: ignore[method-assign]

    return router


# ── REST Endpoints ─────────────────────────────────────────


@router.get("", response_model=RuntimeEventListResponse)
async def get_events(
    limit: int = Query(50, ge=1, le=500),
    runtime_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
):
    """Retrieve recent runtime events with optional filters."""
    if _bus is None:
        return RuntimeEventListResponse(events=[], total=0)

    events = _bus.get_recent_events(limit)

    # Apply filters
    if runtime_id:
        events = [e for e in events if e.runtime_id == runtime_id]
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    if severity:
        events = [
            e
            for e in events
            if e.severity.value == severity
            or (
                severity == "critical"
                and e.severity == RuntimeEventSeverity.CRITICAL
            )
        ]

    return RuntimeEventListResponse(
        events=[_event_to_response(e) for e in events[:limit]],
        total=len(events),
        runtime_id=runtime_id,
    )


@router.get("/{runtime_id}", response_model=RuntimeEventListResponse)
async def get_runtime_events(
    runtime_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Retrieve event history for a specific runtime."""
    if _bus is None:
        return RuntimeEventListResponse(events=[], total=0, runtime_id=runtime_id)

    events = _bus.get_runtime_history(runtime_id, limit)
    return RuntimeEventListResponse(
        events=[_event_to_response(e) for e in events],
        total=len(events),
        runtime_id=runtime_id,
    )


@router.post("", response_model=RuntimeEventResponse)
async def create_event(request: RuntimeEventCreateRequest):
    """Publish a new runtime event via the API."""
    if _bus is None:
        raise RuntimeError("RuntimeEventBus not initialised")

    event = RuntimeEventModel(
        runtime_id=request.runtime_id,
        event_type=request.event_type,
        severity=request.severity,
        source=request.source,
        payload=request.payload,
        correlation_id=request.correlation_id,
    )
    _bus.publish(event)
    return _event_to_response(event)


# ── WebSocket ──────────────────────────────────────────────


@router.websocket("/ws")
async def runtime_events_ws(websocket: WebSocket):
    """Stream runtime events in real time.

    Query params:
        - runtime_id (optional): filter by runtime
        - severity (optional): minimum severity level
    """
    await websocket.accept()
    _ws_clients.append(websocket)

    runtime_filter: Optional[str] = None
    severity_filter: Optional[str] = None

    try:
        # Read initial filter params from the client
        data = await websocket.receive_json()
        if isinstance(data, dict):
            runtime_filter = data.get("runtime_id")
            severity_filter = data.get("severity")

        # Send a confirmation
        await websocket.send_json({
            "type": "connected",
            "runtime_id": runtime_filter,
            "severity": severity_filter,
        })

        # Keep the connection alive and listen for filter updates
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict):
                if "runtime_id" in data:
                    runtime_filter = data["runtime_id"]
                if "severity" in data:
                    severity_filter = data["severity"]

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── Internal ───────────────────────────────────────────────


def _event_to_response(event: RuntimeEventModel) -> RuntimeEventResponse:
    return RuntimeEventResponse(
        id=event.id,
        runtime_id=event.runtime_id,
        event_type=event.event_type,
        severity=event.severity.value,
        timestamp=event.timestamp.isoformat(),
        source=event.source,
        payload=event.payload,
        correlation_id=event.correlation_id,
    )


async def _broadcast(event: RuntimeEventModel) -> None:
    """Send an event to all connected WebSocket clients."""
    payload = _event_to_response(event).model_dump()
    message = json.dumps(payload)
    stale: list[WebSocket] = []

    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)

    for ws in stale:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
