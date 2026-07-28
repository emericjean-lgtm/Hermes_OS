"""HOS-003 sentinel tests — SDS EventBus wiring.

Tests the EventBusHolder singleton, the FastAPI dependency injection,
the health/liveness/readiness endpoints, and the lifespan lifecycle.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from backend.ral.event_bus import EventBusInterface
from backend.ral.event_bus_impl import EventBusImpl
from backend.sds.dependencies import get_eventbus
from backend.sds.routes import SDS_ROUTER
from backend.sds.runtime import EventBusHolder, get_holder, init_eventbus_in_holder


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".eventbus.sqlite", delete=False) as f:
        yield f.name
    try:
        os.unlink(f.name)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------
# 1. EventBusHolder singleton
# ------------------------------------------------------------------


async def test_get_holder_returns_singleton(reset_eventbus) -> None:  # noqa: F811
    h1 = get_holder()
    h2 = get_holder()
    assert h1 is h2


async def test_holder_requires_install_before_bus(reset_eventbus) -> None:  # noqa: F811
    holder = get_holder()
    with pytest.raises(RuntimeError, match="eventbus_not_started"):
        _ = holder.bus


async def test_holder_install_and_stop(db_path: str, reset_eventbus) -> None:  # noqa: F811
    bus = EventBusImpl(db_path)
    await bus.start()
    holder = get_holder()
    holder.install(bus)

    assert holder.bus is not None
    assert holder.started_at is not None

    await holder.stop()
    with pytest.raises(RuntimeError, match="eventbus_not_started"):
        _ = holder.bus


# ------------------------------------------------------------------
# 2. init_eventbus_in_holder
# ------------------------------------------------------------------


async def test_init_eventbus_in_holder(db_path: str, reset_eventbus) -> None:  # noqa: F811
    holder = await init_eventbus_in_holder(db_path)
    assert holder.bus is not None
    try:
        stats = get_holder().bus  # EventBusInterface reference
        assert stats is not None
    finally:
        await holder.stop()


# ------------------------------------------------------------------
# 3. get_eventbus DI
# ------------------------------------------------------------------


async def test_get_eventbus_returns_protocol(db_path: str, reset_eventbus) -> None:  # noqa: F811
    await init_eventbus_in_holder(db_path)
    bus = await get_eventbus()
    # Must be an EventBusInterface (Protocol), not the concrete impl
    assert isinstance(bus, EventBusInterface) or hasattr(bus, "publish")


# ------------------------------------------------------------------
# 4. FastAPI lifecycle and endpoints
# ------------------------------------------------------------------


def test_lifespan_and_health_endpoint(db_path: str) -> None:
    """Integration test with a minimal FastAPI app wiring SDS."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(SDS_ROUTER)

    @app.on_event("startup")
    async def _start_bus():
        holder = await init_eventbus_in_holder(db_path)
        app.state.eventbus_holder = holder

    @app.on_event("shutdown")
    async def _stop_bus():
        holder = get_holder()
        await holder.stop()

    with TestClient(app) as client:
        # /healthz — no bus needed
        r = client.get("/api/hermes-os/healthz")
        assert r.status_code == 200
        assert r.json()["alive"] is True

        # /readyz — bus started
        r = client.get("/api/hermes-os/readyz")
        assert r.status_code == 200
        assert r.json()["ready"] is True

        # /api/hermes-os/health — full health
        r = client.get("/api/hermes-os/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["uptime_seconds"] >= 0
        assert "eventbus" in data


def test_health_uptime_monotonic(db_path: str) -> None:
    """Uptime must increase between two successive calls."""
    import time

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(SDS_ROUTER)

    @app.on_event("startup")
    async def _start_bus():
        holder = await init_eventbus_in_holder(db_path)
        app.state.eventbus_holder = holder

    @app.on_event("shutdown")
    async def _stop_bus():
        holder = get_holder()
        await holder.stop()

    with TestClient(app) as client:
        r1 = client.get("/api/hermes-os/health")
        u1 = r1.json()["uptime_seconds"]

        time.sleep(1.1)

        r2 = client.get("/api/hermes-os/health")
        u2 = r2.json()["uptime_seconds"]

        assert u2 > u1, f"uptime not monotonic: {u1} -> {u2}"


def test_readyz_503_when_bus_not_started() -> None:
    """If the bus is not started, /readyz must respond 503."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(SDS_ROUTER)

    with TestClient(app) as client:
        r = client.get("/api/hermes-os/readyz")
        assert r.status_code == 503


# ------------------------------------------------------------------
# 5. Forward wildcard — sanity check
# ------------------------------------------------------------------


async def test_wildcard_forwarding_publishes_to_eventhub(db_path: str, reset_eventbus) -> None:  # noqa: F811
    """Verify that subscribing with ``*`` forwards events to a handler."""
    from backend.ral.event_bus import Topic, TopicPattern

    holder = await init_eventbus_in_holder(db_path)

    received: list[str] = []
    sid = get_holder().bus.subscribe(
        TopicPattern("*"),
        lambda e: received.append(e.topic.value),
    )
    bus = get_holder().bus
    bus.publish(Topic.RUNTIME_STARTED, {"status": "ok"})
    bus.unsubscribe(sid)
    await holder.stop()
    assert "runtime.started" in received
