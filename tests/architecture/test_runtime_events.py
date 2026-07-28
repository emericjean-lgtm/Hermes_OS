"""HOS-013 sentinel tests — Runtime Event Bus & Observability Layer.

Tests the in-memory event bus and observability layer without any
network call or concrete backend.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from backend.ral.runtime import CapabilitySet
from backend.ral.runtime_events import (
    RuntimeEvent,
    RuntimeEventBus,
    RuntimeEventType,
    RuntimeObservability,
    Severity,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def bus() -> RuntimeEventBus:
    return RuntimeEventBus(max_events=100)


# -----------------------------------------------------------------------------
# Event creation
# -----------------------------------------------------------------------------


def test_event_creation_defaults() -> None:
    event = RuntimeEvent(
        event_type=RuntimeEventType.REGISTERED,
        runtime_name="stub",
        message="registered",
    )
    assert event.event_type == RuntimeEventType.REGISTERED
    assert event.runtime_name == "stub"
    assert event.message == "registered"
    assert event.severity == Severity.INFO
    assert event.timestamp > 0


def test_event_creation_with_metadata() -> None:
    event = RuntimeEvent(
        event_type=RuntimeEventType.FAILED,
        runtime_name="ollama",
        severity=Severity.ERROR,
        message="boom",
        metadata={"capability": "chat", "latency_ms": 12},
    )
    assert event.severity == Severity.ERROR
    assert event.metadata["capability"] == "chat"


# -----------------------------------------------------------------------------
# Publish / subscribe
# -----------------------------------------------------------------------------


def test_publish_delivers_to_subscribers(bus: RuntimeEventBus) -> None:
    received: list[RuntimeEvent] = []
    bus.subscribe(lambda event: received.append(event))

    event = RuntimeEvent(RuntimeEventType.REGISTERED, "stub")
    bus.publish(event)

    assert len(received) == 1
    assert received[0] is event


def test_publish_to_multiple_subscribers(bus: RuntimeEventBus) -> None:
    received_a: list[RuntimeEvent] = []
    received_b: list[RuntimeEvent] = []
    bus.subscribe(lambda event: received_a.append(event))
    bus.subscribe(lambda event: received_b.append(event))

    event = RuntimeEvent(RuntimeEventType.STARTED, "stub")
    bus.publish(event)

    assert len(received_a) == len(received_b) == 1
    assert received_a[0] is event
    assert received_b[0] is event


def test_get_events_filtered(bus: RuntimeEventBus) -> None:
    bus.publish(RuntimeEvent(RuntimeEventType.REGISTERED, "stub"))
    bus.publish(RuntimeEvent(RuntimeEventType.FAILED, "ollama"))
    bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub"))

    assert len(bus.get_events(event_type=RuntimeEventType.REGISTERED)) == 1
    assert len(bus.get_events(runtime_name="stub")) == 2
    assert len(bus.get_events(event_type=RuntimeEventType.FAILED, runtime_name="ollama")) == 1


# -----------------------------------------------------------------------------
# History management
# -----------------------------------------------------------------------------


def test_max_events_eviction(bus: RuntimeEventBus) -> None:
    bus = RuntimeEventBus(max_events=3)
    for i in range(5):
        bus.publish(RuntimeEvent(RuntimeEventType.SELECTED, f"rt{i}"))

    events = bus.get_events()
    assert len(events) == 3
    assert events[0].runtime_name == "rt2"
    assert events[-1].runtime_name == "rt4"


def test_clear_removes_events(bus: RuntimeEventBus) -> None:
    bus.publish(RuntimeEvent(RuntimeEventType.SELECTED, "stub"))
    bus.clear()
    assert bus.get_events() == []


def test_clear_keeps_subscribers(bus: RuntimeEventBus) -> None:
    received: list[RuntimeEvent] = []
    bus.subscribe(lambda event: received.append(event))
    bus.clear()
    bus.publish(RuntimeEvent(RuntimeEventType.SELECTED, "stub"))
    assert len(received) == 1


# -----------------------------------------------------------------------------
# Thread safety
# -----------------------------------------------------------------------------


def test_concurrent_publish_is_thread_safe(bus: RuntimeEventBus) -> None:
    received: list[RuntimeEvent] = []
    bus.subscribe(lambda event: received.append(event))

    def publish_many() -> None:
        for i in range(100):
            bus.publish(RuntimeEvent(RuntimeEventType.STARTED, f"rt{i}"))

    threads = [threading.Thread(target=publish_many) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(received) == 500


# -----------------------------------------------------------------------------
# Observability / metrics
# -----------------------------------------------------------------------------


def test_observability_aggregates_success_and_failure(bus: RuntimeEventBus) -> None:
    obs = RuntimeObservability(bus)

    bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 10}))
    bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 30}))
    bus.publish(RuntimeEvent(RuntimeEventType.FAILED, "ollama", metadata={"latency_ms": 5}))
    bus.publish(RuntimeEvent(RuntimeEventType.FALLBACK, "ollama"))

    metrics = obs.metrics
    assert metrics["executions"] == 3
    assert metrics["successes"] == 2
    assert metrics["failures"] == 1
    assert metrics["fallbacks"] == 1
    assert metrics["avg_latency_ms"] == pytest.approx(15.0)


def test_observability_most_used_runtime(bus: RuntimeEventBus) -> None:
    obs = RuntimeObservability(bus)

    for _ in range(3):
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 1}))
    for _ in range(2):
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "ollama", metadata={"latency_ms": 1}))

    assert obs.metrics["most_used_runtime"] == "stub"


def test_observability_most_reliable_runtime(bus: RuntimeEventBus) -> None:
    obs = RuntimeObservability(bus)

    # stub: 3 successes, 1 failure -> 75%
    for _ in range(3):
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub"))
    bus.publish(RuntimeEvent(RuntimeEventType.FAILED, "stub"))

    # ollama: 2 successes only -> 100% (but fewer total)
    for _ in range(2):
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "ollama"))

    assert obs.metrics["most_reliable_runtime"] == "ollama"


# -----------------------------------------------------------------------------
# Integration with router / recovery events
# -----------------------------------------------------------------------------


def test_router_publishes_selected_and_completed_events(bus: RuntimeEventBus) -> None:
    import asyncio

    from backend.ral.adapters.stub_runtime import StubRuntime
    from backend.ral.runtime_context import ActiveRuntimeContext
    from backend.ral.runtime_registry import RuntimeRegistry
    from backend.ral.runtime_router import RuntimeRouter
    from backend.ral.runtime_selector import RuntimeSelector

    class _FakeHolder:
        def __init__(self) -> None:
            self.runtime: object = None  # type: ignore[annotation-unreachable]

        def install(self, runtime: object) -> None:
            self.runtime = runtime

    class _FakeEventBus:
        """Minimal EventBusInterface-compatible bus for the stub runtime."""

        def __init__(self) -> None:
            self.events: list[Any] = []

        def publish(self, topic: Any, payload: Any = None) -> None:
            self.events.append((topic, payload))

    async def _run() -> None:
        registry = RuntimeRegistry()
        stub = StubRuntime(bus=_FakeEventBus())
        registry.register("stub", stub)

        await stub.start()

        holder = _FakeHolder()
        context = ActiveRuntimeContext(registry=registry, holder=holder)
        context.set_active("stub")

        selector = RuntimeSelector(registry)
        router = RuntimeRouter(context, selector, event_bus=bus)

        return await router.chat([{"role": "user", "content": "hi"}])

    response = asyncio.run(_run())

    assert response.content == "[stub-runtime] echo: hi"
    types = [e.event_type for e in bus.get_events()]
    assert RuntimeEventType.SELECTED in types
    assert RuntimeEventType.STARTED in types
    assert RuntimeEventType.COMPLETED in types


def test_recovery_manager_publishes_circuit_opened_and_closed(bus: RuntimeEventBus) -> None:
    from backend.ral.runtime_registry import RuntimeRegistry
    from backend.ral.runtime_recovery import RuntimeRecoveryManager
    from backend.ral.runtime_selector import RuntimeSelector

    registry = RuntimeRegistry()
    selector = RuntimeSelector(registry)
    recovery = RuntimeRecoveryManager(
        registry=registry,
        selector=selector,
        failure_threshold=1,
        event_bus=bus,
    )

    recovery.record_failure("stub", RuntimeError("boom"))
    recovery.record_success("stub")

    types = [e.event_type for e in bus.get_events()]
    assert RuntimeEventType.CIRCUIT_OPENED in types
    assert RuntimeEventType.CIRCUIT_CLOSED in types


# -----------------------------------------------------------------------------
# Severity values
# -----------------------------------------------------------------------------


def test_severity_enum_values() -> None:
    assert Severity.DEBUG == "debug"
    assert Severity.INFO == "info"
    assert Severity.WARNING == "warning"
    assert Severity.ERROR == "error"
    assert Severity.CRITICAL == "critical"
