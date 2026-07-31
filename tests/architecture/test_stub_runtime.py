"""HOS-004 sentinel tests — StubRuntime implementation."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.ral.adapters.stub_runtime import StubRuntime, StubChatCapability
from backend.ral.capabilities import ChatCapability, ChatResponse
from backend.ral.event_bus import Topic
from backend.ral.runtime import RuntimeInterface, RuntimeStatus


# ------------------------------------------------------------------
# 1. Protocol compliance
# ------------------------------------------------------------------


def test_stub_satisfies_runtime_interface():
    """StubRuntime must be recognised by ``RuntimeInterface``."""
    stub = StubRuntime(bus=None)
    assert isinstance(stub, RuntimeInterface)


def test_stub_chat_satisfies_chat_protocol():
    """StubChatCapability must be recognised by ``ChatCapability``."""
    cap = StubChatCapability()
    assert isinstance(cap, ChatCapability)


def test_stub_capabilities_contains_chat():
    stub = StubRuntime(bus=None)
    assert stub.capabilities.available == frozenset({"chat"})


# ------------------------------------------------------------------
# 2. Chat capability
# ------------------------------------------------------------------


async def test_stub_chat_echoes_user_message():
    cap = StubChatCapability()
    result = await cap.chat([{"role": "user", "content": "hello world"}])
    assert isinstance(result, ChatResponse)
    assert "hello world" in result.content


async def test_stub_chat_fallback_when_no_user():
    cap = StubChatCapability()
    result = await cap.chat([{"role": "assistant", "content": "hi"}])
    assert isinstance(result, ChatResponse)
    assert "[stub] no user message" in result.content


# ------------------------------------------------------------------
# 3. get() capability lookup
# ------------------------------------------------------------------


def test_stub_get_chat_returns_capability():
    stub = StubRuntime(bus=None)
    cap = stub.get("chat")
    assert cap is not None
    assert isinstance(cap, StubChatCapability)


def test_stub_get_unknown_returns_none():
    stub = StubRuntime(bus=None)
    assert stub.get("vision") is None
    assert stub.get("terminal") is None


# ------------------------------------------------------------------
# 4. Event publishing (lifecycle)
# ------------------------------------------------------------------


async def test_stub_start_event_published():
    """Start must publish ``RUNTIME_STARTED`` on the injected bus."""
    import tempfile
    from datetime import datetime, timezone

    from backend.ral.event_bus_impl import EventBusImpl

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name
    try:
        bus = EventBusImpl(db)
        await bus.start()
        stub = StubRuntime(bus=bus)
        await stub.start()
        events = []
        async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
            events.append(e)
        await bus.stop()
        assert any(e.topic == Topic.RUNTIME_STARTED for e in events)
    finally:
        os.unlink(db)


async def test_stub_stop_event_published():
    """Stop must publish ``RUNTIME_STOPPED``."""
    import tempfile
    from datetime import datetime, timezone

    from backend.ral.event_bus_impl import EventBusImpl

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name
    try:
        bus = EventBusImpl(db)
        await bus.start()
        stub = StubRuntime(bus=bus)
        await stub.start()
        await stub.stop()
        events = []
        async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
            events.append(e)
        await bus.stop()
        assert any(e.topic == Topic.RUNTIME_STOPPED for e in events)
    finally:
        os.unlink(db)


async def test_stub_event_payload_includes_runtime_and_version():
    import tempfile
    from datetime import datetime, timezone

    from backend.ral.event_bus_impl import EventBusImpl

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db = f.name
    try:
        bus = EventBusImpl(db)
        await bus.start()
        stub = StubRuntime(bus=bus)
        await stub.start()
        events = []
        async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
            events.append(e)
        await bus.stop()
        start_events = [e for e in events if e.topic == Topic.RUNTIME_STARTED]
        assert len(start_events) >= 1
        assert start_events[0].payload.get("runtime") == "stub"
        assert start_events[0].payload.get("version") == "0.1.0"
    finally:
        os.unlink(db)


# ------------------------------------------------------------------
# 5. Lifecycle status
# ------------------------------------------------------------------


async def test_stub_status_after_start():
    stub = StubRuntime(bus=None)
    assert stub.status == RuntimeStatus.STOPPED
    await stub.start()
    assert stub.status == RuntimeStatus.STARTED
    await stub.stop()
    assert stub.status == RuntimeStatus.STOPPED


# ------------------------------------------------------------------
# 6. Runtime holder singleton
# ------------------------------------------------------------------


async def test_runtime_holder_singleton(reset_eventbus):  # noqa: F811
    from backend.sds.runtime import get_runtime_holder

    h1 = get_runtime_holder()
    h2 = get_runtime_holder()
    assert h1 is h2


async def test_runtime_holder_install_and_stop(reset_eventbus):  # noqa: F811
    from backend.sds.runtime import get_runtime_holder

    stub = StubRuntime(bus=None)
    await stub.start()

    holder = get_runtime_holder()
    holder.install(stub)
    assert holder.runtime.name == "stub"

    await holder.stop()
    with pytest.raises(RuntimeError, match="runtime_not_started"):
        _ = holder.runtime


# ------------------------------------------------------------------
# 7. SDS endpoint
# ------------------------------------------------------------------


def test_runtime_endpoint_returns_info(tmp_path, reset_eventbus):  # noqa: F811
    from pathlib import Path

    from fastapi import FastAPI

    from backend.sds.routes import SDS_ROUTER
    from backend.sds.runtime import (
        get_holder,
        get_runtime_holder,
        init_eventbus_in_holder,
    )

    _db = str(Path(tmp_path) / "test_eventbus.sqlite")
    app = FastAPI()
    app.include_router(SDS_ROUTER)

    @app.on_event("startup")
    async def _start():
        # Bus first, then runtime
        await init_eventbus_in_holder(_db)
        bus = get_holder().bus
        stub = StubRuntime(bus=bus)
        await stub.start()
        get_runtime_holder().install(stub)

    @app.on_event("shutdown")
    async def _stop():
        await get_runtime_holder().stop()
        await get_holder().stop()

    with TestClient(app) as client:
        r = client.get("/api/hermes-os/runtime")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "stub"
        assert data["version"] == "0.1.0"
        assert "chat" in data["capabilities"]
        assert data["started"] is True


# ------------------------------------------------------------------
# 8. Regression: baseline tests still pass
# ------------------------------------------------------------------


def test_hos_003_sds_endpoints_still_work(tmp_path, reset_eventbus):  # noqa: F811
    from pathlib import Path

    from fastapi import FastAPI

    from backend.sds.routes import SDS_ROUTER
    from backend.sds.runtime import (
        get_holder,
        init_eventbus_in_holder,
    )

    _db = str(Path(tmp_path) / "test_eventbus.sqlite")
    app = FastAPI()
    app.include_router(SDS_ROUTER)

    @app.on_event("startup")
    async def _start():
        await init_eventbus_in_holder(_db)

    @app.on_event("shutdown")
    async def _stop():
        await get_holder().stop()

    with TestClient(app) as client:
        assert client.get("/api/hermes-os/healthz").status_code == 200
