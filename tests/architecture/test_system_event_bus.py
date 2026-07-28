"""HOS-025 sentinel tests — System Event Bus.

Tests the central event bus's publish/subscribe, filtering, history,
export, statistics, subscriber interface, thread safety, and
compatibility with HOS-013 through HOS-024 event types.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from backend.events.system_event_bus import (
    EventFilter,
    EventHistory,
    EventStatistics,
    EventSubscriber,
    EventSeverity,
    SystemEvent,
    SystemEventBus,
    SystemEventBusError,
    SystemEventType,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_system_event_defaults() -> None:
    ev = SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="test")
    assert ev.id == "e1"
    assert ev.type == SystemEventType.SYSTEM
    assert ev.severity == EventSeverity.INFO
    assert ev.correlation_id == ""


def test_system_event_type_values() -> None:
    assert SystemEventType.RUNTIME.value == "runtime"
    assert SystemEventType.AGENT.value == "agent"
    assert SystemEventType.MISSION.value == "mission"
    assert SystemEventType.EXECUTION.value == "execution"
    assert SystemEventType.MEMORY.value == "memory"
    assert SystemEventType.SKILL.value == "skill"
    assert SystemEventType.SYSTEM.value == "system"
    assert SystemEventType.OBSERVABILITY.value == "observability"
    assert SystemEventType.INTEGRATION.value == "integration"


def test_event_severity_values() -> None:
    assert EventSeverity.DEBUG.value == "debug"
    assert EventSeverity.INFO.value == "info"
    assert EventSeverity.WARNING.value == "warning"
    assert EventSeverity.ERROR.value == "error"
    assert EventSeverity.CRITICAL.value == "critical"


def test_event_statistics_defaults() -> None:
    stats = EventStatistics()
    assert stats.total_published == 0
    assert stats.subscriber_count == 0
    assert stats.history_size == 0


def test_event_filter_defaults() -> None:
    f = EventFilter()
    assert f.types is None
    assert f.limit is None
    assert f.offset == 0


# ============================================================================
# EventHistory
# ============================================================================


def test_history_append_and_search() -> None:
    history = EventHistory(max_events=100)
    assert history.size == 0

    ev = SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="test")
    history.append(ev)
    assert history.size == 1

    results = history.search()
    assert len(results) == 1
    assert results[0].id == "e1"


def test_history_max_events() -> None:
    history = EventHistory(max_events=3)
    for i in range(5):
        history.append(SystemEvent(
            id=f"e{i}", type=SystemEventType.SYSTEM, source="test",
        ))
    assert history.size == 3


def test_history_clear() -> None:
    history = EventHistory()
    history.append(SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="test"))
    history.clear()
    assert history.size == 0


def test_history_search_with_filter() -> None:
    history = EventHistory()
    history.append(SystemEvent(id="e1", type=SystemEventType.RUNTIME, source="runtime"))
    history.append(SystemEvent(id="e2", type=SystemEventType.MEMORY, source="memory"))
    history.append(SystemEvent(id="e3", type=SystemEventType.RUNTIME, source="runtime"))

    # Filter by type.
    filter_ = EventFilter(types=frozenset({SystemEventType.RUNTIME}))
    results = history.search(filter_)
    assert len(results) == 2
    assert {r.id for r in results} == {"e1", "e3"}


def test_history_search_with_source_filter() -> None:
    history = EventHistory()
    history.append(SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="alpha"))
    history.append(SystemEvent(id="e2", type=SystemEventType.SYSTEM, source="beta"))

    filter_ = EventFilter(sources=frozenset({"alpha"}))
    results = history.search(filter_)
    assert len(results) == 1
    assert results[0].id == "e1"


def test_history_search_with_correlation() -> None:
    history = EventHistory()
    history.append(SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="t",
                                correlation_id="corr_1"))
    history.append(SystemEvent(id="e2", type=SystemEventType.SYSTEM, source="t"))

    filter_ = EventFilter(correlation_id="corr_1")
    results = history.search(filter_)
    assert len(results) == 1


def test_history_search_with_time_range() -> None:
    history = EventHistory()
    now = time.time()
    history.append(SystemEvent(id="e1", type=SystemEventType.SYSTEM, source="t",
                                timestamp=now - 10))
    history.append(SystemEvent(id="e2", type=SystemEventType.SYSTEM, source="t",
                                timestamp=now))

    filter_ = EventFilter(since=now - 5)
    results = history.search(filter_)
    assert len(results) == 1
    assert results[0].id == "e2"


def test_history_export_json() -> None:
    history = EventHistory()
    history.append(SystemEvent(id="e1", type=SystemEventType.RUNTIME, source="r"))
    exported = history.export()
    data = json.loads(exported)
    assert len(data) == 1
    assert data[0]["id"] == "e1"
    assert data[0]["type"] == "runtime"


# ============================================================================
# SystemEventBus — publish
# ============================================================================


def test_bus_publish_returns_event() -> None:
    bus = SystemEventBus()
    ev = bus.publish(SystemEventType.SYSTEM, "test", payload={"key": "val"})
    assert ev.id is not None
    assert ev.type == SystemEventType.SYSTEM
    assert ev.payload == {"key": "val"}


def test_bus_publish_stores_in_history() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.RUNTIME, "test")
    results = bus.query()
    assert len(results) == 1


def test_bus_publish_with_severity() -> None:
    bus = SystemEventBus()
    ev = bus.publish(SystemEventType.SYSTEM, "test",
                     severity=EventSeverity.ERROR)
    assert ev.severity == EventSeverity.ERROR


def test_bus_publish_with_correlation() -> None:
    bus = SystemEventBus()
    ev = bus.publish(SystemEventType.MISSION, "supervisor",
                     correlation_id="corr_x")
    assert ev.correlation_id == "corr_x"


# ============================================================================
# SystemEventBus — subscribe
# ============================================================================


def test_bus_subscribe_callback() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    bus.subscribe(handler)
    bus.publish(SystemEventType.SYSTEM, "test")

    assert len(received) == 1
    assert received[0].type == SystemEventType.SYSTEM


def test_bus_subscribe_with_filter() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    filter_ = EventFilter(types=frozenset({SystemEventType.RUNTIME}))
    bus.subscribe(handler, filter_=filter_)

    bus.publish(SystemEventType.MEMORY, "mem")
    bus.publish(SystemEventType.RUNTIME, "run")

    assert len(received) == 1
    assert received[0].type == SystemEventType.RUNTIME


def test_bus_subscribe_filter_by_source() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    filter_ = EventFilter(sources=frozenset({"alpha"}))
    bus.subscribe(handler, filter_=filter_)

    bus.publish(SystemEventType.SYSTEM, "beta")
    bus.publish(SystemEventType.SYSTEM, "alpha")

    assert len(received) == 1
    assert received[0].source == "alpha"


def test_bus_subscribe_filter_by_severity() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    filter_ = EventFilter(severities=frozenset({EventSeverity.ERROR}))
    bus.subscribe(handler, filter_=filter_)

    bus.publish(SystemEventType.SYSTEM, "t", severity=EventSeverity.INFO)
    bus.publish(SystemEventType.SYSTEM, "t", severity=EventSeverity.ERROR)

    assert len(received) == 1
    assert received[0].severity == EventSeverity.ERROR


def test_bus_unsubscribe() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    bus.subscribe(handler)
    bus.unsubscribe(handler)
    bus.publish(SystemEventType.SYSTEM, "test")

    assert len(received) == 0


def test_bus_unsubscribe_unknown_returns_false() -> None:
    bus = SystemEventBus()

    def handler(event: SystemEvent) -> None:
        pass

    result = bus.unsubscribe(handler)
    assert result is False


# ============================================================================
# SystemEventBus — EventSubscriber interface
# ============================================================================


class CollectingSubscriber(EventSubscriber):
    def __init__(self) -> None:
        self.events: list[SystemEvent] = []

    def handle_event(self, event: SystemEvent) -> None:
        self.events.append(event)


def test_bus_subscribe_event_subscriber() -> None:
    bus = SystemEventBus()
    sub = CollectingSubscriber()

    bus.subscribe(sub)
    bus.publish(SystemEventType.SYSTEM, "test")

    assert len(sub.events) == 1


def test_bus_subscribe_event_subscriber_with_filter() -> None:
    bus = SystemEventBus()
    sub = CollectingSubscriber()

    filter_ = EventFilter(types=frozenset({SystemEventType.RUNTIME}))
    bus.subscribe(sub, filter_=filter_)

    bus.publish(SystemEventType.MEMORY, "mem")
    bus.publish(SystemEventType.RUNTIME, "run")

    assert len(sub.events) == 1
    assert sub.events[0].type == SystemEventType.RUNTIME


def test_bus_subscriber_name_default() -> None:
    sub = CollectingSubscriber()
    assert sub.name == "CollectingSubscriber"


def test_bus_subscribe_invalid_raises() -> None:
    bus = SystemEventBus()
    with pytest.raises(SystemEventBusError, match="callable or"):
        bus.subscribe("not_callable")  # type: ignore[arg-type]


# ============================================================================
# SystemEventBus — broadcast
# ============================================================================


def test_bus_broadcast_delivers_to_all() -> None:
    bus = SystemEventBus()
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    # Even with a restrictive filter, broadcast delivers.
    filter_ = EventFilter(types=frozenset({SystemEventType.RUNTIME}))
    bus.subscribe(handler, filter_=filter_)

    bus.broadcast(SystemEventType.MEMORY, "mem")

    assert len(received) == 1


# ============================================================================
# SystemEventBus — query / clear / export
# ============================================================================


def test_bus_query_all() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.RUNTIME, "r1")
    bus.publish(SystemEventType.MEMORY, "m1")
    results = bus.query()
    assert len(results) == 2


def test_bus_query_filtered() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.RUNTIME, "r1")
    bus.publish(SystemEventType.MEMORY, "m1")

    f = EventFilter(types=frozenset({SystemEventType.RUNTIME}))
    results = bus.query(f)
    assert len(results) == 1


def test_bus_clear() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.SYSTEM, "t")
    bus.clear()
    results = bus.query()
    assert len(results) == 0


def test_bus_export() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.RUNTIME, "r")
    exported = bus.export()
    data = json.loads(exported)
    assert len(data) == 1
    assert data[0]["type"] == "runtime"


# ============================================================================
# SystemEventBus — statistics
# ============================================================================


def test_bus_statistics_initial() -> None:
    bus = SystemEventBus()
    stats = bus.statistics()
    assert stats.total_published == 0
    assert stats.subscriber_count == 0


def test_bus_statistics_after_publish() -> None:
    bus = SystemEventBus()
    bus.publish(SystemEventType.RUNTIME, "r")
    bus.publish(SystemEventType.MEMORY, "m")

    stats = bus.statistics()
    assert stats.total_published == 2
    assert stats.history_size == 2
    assert "runtime" in stats.events_by_type
    assert "memory" in stats.events_by_type


def test_bus_statistics_with_subscriber() -> None:
    bus = SystemEventBus()

    def handler(event: SystemEvent) -> None:
        pass

    bus.subscribe(handler)
    bus.publish(SystemEventType.SYSTEM, "t")

    stats = bus.statistics()
    assert stats.subscriber_count == 1
    assert stats.total_published == 1
    assert stats.total_consumed == 1


# ============================================================================
# SystemEventBus — integration helpers
# ============================================================================


def test_from_runtime_event_type() -> None:
    result = SystemEventBus.from_runtime_event_type("runtime.started")
    assert result == SystemEventType.RUNTIME


def test_from_memory_event() -> None:
    result = SystemEventBus.from_memory_event("memory.stored")
    assert result == SystemEventType.MEMORY


def test_from_skill_event() -> None:
    result = SystemEventBus.from_skill_event("skill.loaded")
    assert result == SystemEventType.SKILL


def test_from_supervisor_event() -> None:
    result = SystemEventBus.from_supervisor_event("supervisor.mission_created")
    assert result == SystemEventType.MISSION


def test_from_lifecycle_event() -> None:
    result = SystemEventBus.from_lifecycle_event("lifecycle.created")
    assert result == SystemEventType.AGENT


def test_from_execution_event() -> None:
    result = SystemEventBus.from_execution_event("execution.started")
    assert result == SystemEventType.EXECUTION


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_publish_and_query() -> None:
    bus = SystemEventBus()
    errors: list[Exception] = []

    def publisher() -> None:
        for i in range(100):
            try:
                bus.publish(SystemEventType.SYSTEM, f"pub_{i % 5}")
            except Exception as e:
                errors.append(e)

    def querier() -> None:
        for _ in range(50):
            try:
                bus.query()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=publisher)
    t2 = threading.Thread(target=querier)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    stats = bus.statistics()
    assert stats.total_published == 100


def test_concurrent_subscribe_and_publish() -> None:
    bus = SystemEventBus()
    errors: list[Exception] = []
    received: list[SystemEvent] = []

    def handler(event: SystemEvent) -> None:
        received.append(event)

    def subscriber() -> None:
        for i in range(20):
            try:
                bus.subscribe(handler)
            except Exception as e:
                errors.append(e)

    def publisher() -> None:
        for i in range(50):
            try:
                bus.publish(SystemEventType.SYSTEM, "t")
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=subscriber)
    t2 = threading.Thread(target=publisher)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors


def test_concurrent_subscribe_and_unsubscribe() -> None:
    bus = SystemEventBus()
    errors: list[Exception] = []
    handlers = []

    def subscriber() -> None:
        for i in range(30):
            def make_handler() -> callable:
                def h(event: SystemEvent) -> None:
                    pass
                return h
            h = make_handler()
            handlers.append(h)
            try:
                bus.subscribe(h)
            except Exception as e:
                errors.append(e)

    def unsubscriber() -> None:
        for _ in range(10):
            if handlers:
                h = handlers.pop(0)
                try:
                    bus.unsubscribe(h)
                except Exception as e:
                    errors.append(e)

    t1 = threading.Thread(target=subscriber)
    t2 = threading.Thread(target=unsubscriber)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
