"""GET /ws — the real-time channel of cahier des charges §24.2.

One WebSocket, every event type, optionally filtered by the client:

    ws://host/ws                       → everything
    ws://host/ws?types=task.update     → only task updates

Each frame is `{"type", "payload", "timestamp"}`.

`system.metrics` is produced here rather than by the GPU monitor: §24.2
asks for it every 2 s regardless of what anyone is doing, which is a
property of the *channel*, not of the monitor. The ticker only runs while
someone is connected — polling a GPU for an empty room wakes the card
every 2 s for nothing.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.event_hub import EVENT_TYPES, get_event_hub
from backend.monitoring.gpu_monitor import get_gpu_monitor

logger = logging.getLogger(__name__)

router = APIRouter()

METRICS_INTERVAL_SECONDS = 2.0

_metrics_task: asyncio.Task | None = None


async def _metrics_ticker() -> None:
    """Push system.metrics on the §24.2 cadence while clients are connected."""
    hub = get_event_hub()
    while True:
        try:
            snapshot = await get_gpu_monitor().snapshot()
            hub.publish("system.metrics", snapshot.to_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            # A GPU read can fail transiently (driver busy, tool missing).
            # It must not kill the ticker, or metrics stop for the whole
            # session after one hiccup — and nothing would say why.
            logger.exception("system.metrics snapshot failed")
        await asyncio.sleep(METRICS_INTERVAL_SECONDS)


def _ensure_ticker() -> None:
    global _metrics_task
    if _metrics_task is None or _metrics_task.done():
        _metrics_task = asyncio.create_task(_metrics_ticker())


def _stop_ticker_if_idle() -> None:
    global _metrics_task
    if get_event_hub().subscriber_count == 0 and _metrics_task is not None:
        _metrics_task.cancel()
        _metrics_task = None


def _parse_types(raw: str | None) -> frozenset[str] | None:
    """Unknown names are rejected rather than ignored: a client filtering
    on a typo would otherwise sit forever on a silent socket, looking
    exactly like a channel with nothing to report."""
    if not raw:
        return None
    requested = frozenset(part.strip() for part in raw.split(",") if part.strip())
    unknown = requested - EVENT_TYPES
    if unknown:
        raise ValueError(
            f"unknown event type(s): {', '.join(sorted(unknown))}. "
            f"Known types: {', '.join(sorted(EVENT_TYPES))}"
        )
    return requested or None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    try:
        types = _parse_types(websocket.query_params.get("types"))
    except ValueError as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "payload": {"detail": str(exc)}})
        await websocket.close(code=1008)
        return

    await websocket.accept()
    hub = get_event_hub()
    _ensure_ticker()

    try:
        # aclosing, not a bare `async for`: leaving an async generator to
        # be finalised by the garbage collector would leave this client
        # subscribed for an indeterminate time after it disconnected — the
        # hub would keep queueing for nobody, and the metrics ticker would
        # never see the room empty out.
        async with contextlib.aclosing(hub.subscribe(types)) as events:
            async for event in events:
                await websocket.send_json(event.to_dict())
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("websocket closed on error")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
    finally:
        _stop_ticker_if_idle()
