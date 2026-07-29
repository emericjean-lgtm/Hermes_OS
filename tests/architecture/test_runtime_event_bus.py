"""Tests for the Runtime Event Bus & Observability (HOS-034)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone

import pytest

from backend.runtime.events.event_bus import RuntimeEventBus
from backend.runtime.events.event_models import (
    RuntimeEventModel,
    RuntimeEventSeverity,
)
from backend.runtime.events.event_store import SQLEventStore
from backend.runtime.events.event_types import (
    RuntimeEventType,
    ALL_RUNTIME_EVENT_TYPES,
    RUNTIME_EVENT_CATEGORIES,
)


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def bus() -> RuntimeEventBus:
    return RuntimeEventBus(max_history=100)


@pytest.fixture
def sample_event() -> RuntimeEventModel:
    return RuntimeEventModel(
        runtime_id="ollama-qwen3-14b",
        event_type=RuntimeEventType.RUNTIME_STARTED.value,
        severity=RuntimeEventSeverity.INFO,
        payload={"model": "qwen3:14b", "vram_gb": 16},
    )


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield f.name
    try:
        os.unlink(f.name)
    except OSError:
        pass


# ─── 1. Event Creation Tests ───────────────────────────────


class TestEventCreation:
    def test_create_default_event(self):
        """Event is created with default values."""
        event = RuntimeEventModel(runtime_id="test", event_type="runtime.started")
        assert event.id is not None
        assert len(event.id) == 32
        assert event.severity == RuntimeEventSeverity.INFO
        assert event.source == "runtime"
        assert event.payload == {}
        assert event.correlation_id is None

    def test_create_critical_event(self):
        """Event with CRITICAL severity."""
        event = RuntimeEventModel(
            runtime_id="test",
            event_type="runtime.failed",
            severity=RuntimeEventSeverity.CRITICAL,
            payload={"error": "OOM"},
        )
        assert event.severity == RuntimeEventSeverity.CRITICAL
        assert event.payload["error"] == "OOM"
        assert event.runtime_id == "test"

    def test_create_with_correlation(self):
        """Event with correlation_id."""
        event = RuntimeEventModel(
            runtime_id="test",
            event_type="routing.fallback",
            correlation_id="mission-42",
        )
        assert event.correlation_id == "mission-42"

    def test_dict_safe(self, sample_event):
        """dict_safe() returns JSON-safe dict."""
        d = sample_event.dict_safe()
        assert d["id"] == sample_event.id
        assert d["runtime_id"] == "ollama-qwen3-14b"
        assert d["event_type"] == "runtime.started"
        assert d["severity"] == "info"
        assert isinstance(d["timestamp"], str)
        assert "T" in d["timestamp"]
        assert isinstance(d["payload"], dict)


# ─── 2. Event Bus Publish/Subscribe Tests ──────────────────


class TestEventBus:
    def test_publish_stores_event(self, bus: RuntimeEventBus, sample_event: RuntimeEventModel):
        """Published event is stored in history."""
        bus.publish(sample_event)
        assert bus.event_count == 1
        recent = bus.get_recent_events(10)
        assert len(recent) == 1
        assert recent[0].id == sample_event.id

    def test_publish_multiple_events(self, bus: RuntimeEventBus):
        """Multiple events are stored in order."""
        for i in range(5):
            bus.publish(RuntimeEventModel(
                runtime_id="test",
                event_type="runtime.started",
                payload={"index": i},
            ))
        assert bus.event_count == 5
        recent = bus.get_recent_events(10)
        assert len(recent) == 5

    def test_subscribe_receives_event(self, bus: RuntimeEventBus, sample_event: RuntimeEventModel):
        """Subscriber receives published event."""
        received: list[RuntimeEventModel] = []

        def handler(event: RuntimeEventModel) -> None:
            received.append(event)

        bus.subscribe(handler)
        bus.publish(sample_event)
        time.sleep(0.01)  # Allow handler dispatch
        assert len(received) == 1
        assert received[0].id == sample_event.id

    def test_subscribe_with_filter(self, bus: RuntimeEventBus):
        """Subscriber only receives matching event types."""
        received: list[RuntimeEventModel] = []

        def handler(event: RuntimeEventModel) -> None:
            received.append(event)

        bus.subscribe(handler, event_types=["runtime.started"])
        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.stopped"))
        time.sleep(0.01)
        assert len(received) == 1
        assert received[0].event_type == "runtime.started"

    def test_unsubscribe_stops_receiving(self, bus: RuntimeEventBus):
        """Unsubscribed handler no longer receives events."""
        received: list[RuntimeEventModel] = []

        def handler(event: RuntimeEventModel) -> None:
            received.append(event)

        bus.subscribe(handler)
        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        bus.unsubscribe(handler)
        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.stopped"))
        time.sleep(0.01)
        assert len(received) == 1  # Only the first event

    def test_multiple_subscribers(self, bus: RuntimeEventBus):
        """Multiple subscribers all receive the event."""
        received1: list[RuntimeEventModel] = []
        received2: list[RuntimeEventModel] = []

        bus.subscribe(lambda e: received1.append(e))
        bus.subscribe(lambda e: received2.append(e))
        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        time.sleep(0.01)
        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0].id == received2[0].id

    def test_history_limit(self):
        """History is bounded by max_history."""
        bus = RuntimeEventBus(max_history=10)
        for i in range(20):
            bus.publish(RuntimeEventModel(
                runtime_id="test",
                event_type="runtime.started",
                payload={"index": i},
            ))
        assert bus.event_count == 10
        recent = bus.get_recent_events(100)
        assert len(recent) == 10

    def test_clear_history(self, bus: RuntimeEventBus, sample_event: RuntimeEventModel):
        """Clear removes all in-memory events."""
        bus.publish(sample_event)
        assert bus.event_count == 1
        bus.clear()
        assert bus.event_count == 0

    def test_get_runtime_history(self, bus: RuntimeEventBus):
        """get_runtime_history filters by runtime_id."""
        bus.publish(RuntimeEventModel(runtime_id="runtime-a", event_type="runtime.started"))
        bus.publish(RuntimeEventModel(runtime_id="runtime-b", event_type="runtime.started"))
        bus.publish(RuntimeEventModel(runtime_id="runtime-a", event_type="runtime.stopped"))

        history_a = bus.get_runtime_history("runtime-a")
        assert len(history_a) == 2
        assert all(e.runtime_id == "runtime-a" for e in history_a)

        history_b = bus.get_runtime_history("runtime-b")
        assert len(history_b) == 1


# ─── 3. Event Store Tests ──────────────────────────────────


class TestSQLEventStore:
    def test_store_and_retrieve(self, db_path: str):
        """Stored event is retrievable."""
        store = SQLEventStore(db_path)
        event = RuntimeEventModel(runtime_id="test", event_type="runtime.started")
        store.store(event)
        recent = store.get_recent(10)
        assert len(recent) == 1
        assert recent[0].id == event.id
        store.close()

    def test_get_by_runtime(self, db_path: str):
        """get_by_runtime filters correctly."""
        store = SQLEventStore(db_path)
        store.store(RuntimeEventModel(runtime_id="a", event_type="runtime.started"))
        store.store(RuntimeEventModel(runtime_id="b", event_type="runtime.started"))
        store.store(RuntimeEventModel(runtime_id="a", event_type="runtime.stopped"))

        results = store.get_by_runtime("a")
        assert len(results) == 2
        assert all(e.runtime_id == "a" for e in results)
        store.close()

    def test_get_by_type(self, db_path: str):
        """get_by_type filters by event type."""
        store = SQLEventStore(db_path)
        store.store(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        store.store(RuntimeEventModel(runtime_id="test", event_type="runtime.stopped"))
        store.store(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))

        results = store.get_by_type("runtime.started")
        assert len(results) == 2
        assert all(e.event_type == "runtime.started" for e in results)
        store.close()

    def test_count(self, db_path: str):
        """count returns total stored events."""
        store = SQLEventStore(db_path)
        assert store.count() == 0
        store.store(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        store.store(RuntimeEventModel(runtime_id="test", event_type="runtime.stopped"))
        assert store.count() == 2
        store.close()

    def test_connection_reuse(self, db_path: str):
        """Multiple operations reuse the same connection."""
        store = SQLEventStore(db_path)
        for i in range(10):
            store.store(RuntimeEventModel(
                runtime_id="test",
                event_type="runtime.started",
                payload={"idx": i},
            ))
        assert store.count() == 10
        recent = store.get_recent(5)
        assert len(recent) == 5
        store.close()

    def test_get_by_severity(self, db_path: str):
        """get_by_severity filters correctly."""
        store = SQLEventStore(db_path)
        store.store(RuntimeEventModel(
            runtime_id="test", event_type="runtime.info",
            severity=RuntimeEventSeverity.INFO,
        ))
        store.store(RuntimeEventModel(
            runtime_id="test", event_type="runtime.warning",
            severity=RuntimeEventSeverity.WARNING,
        ))
        store.store(RuntimeEventModel(
            runtime_id="test", event_type="runtime.error",
            severity=RuntimeEventSeverity.ERROR,
        ))

        results = store.get_by_severity(RuntimeEventSeverity.WARNING)
        assert len(results) >= 2  # WARNING and ERROR
        severities = {e.severity for e in results}
        assert RuntimeEventSeverity.INFO not in severities
        store.close()


# ─── 4. Thread Safety Tests ────────────────────────────────


class TestThreadSafety:
    def test_concurrent_publish(self):
        """Multiple threads can publish simultaneously."""
        bus = RuntimeEventBus(max_history=500)
        errors: list[Exception] = []
        barrier = threading.Barrier(10)

        def publisher() -> None:
            barrier.wait()
            for _ in range(20):
                try:
                    bus.publish(RuntimeEventModel(
                        runtime_id="test",
                        event_type="runtime.started",
                    ))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=publisher) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert bus.event_count == 200

    def test_concurrent_subscribe(self, bus: RuntimeEventBus):
        """Multiple threads can subscribe and receive events."""
        received: list[RuntimeEventModel] = []
        lock = threading.Lock()

        def subscriber() -> None:
            def handler(event: RuntimeEventModel) -> None:
                with lock:
                    received.append(event)
            bus.subscribe(handler)

        threads = [threading.Thread(target=subscriber) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        bus.publish(RuntimeEventModel(runtime_id="test", event_type="runtime.started"))
        time.sleep(0.02)
        assert len(received) == 5

    def test_concurrent_publish_and_query(self):
        """Reads and writes don't deadlock."""
        bus = RuntimeEventBus(max_history=100)
        errors: list[Exception] = []

        def writer() -> None:
            for _ in range(50):
                try:
                    bus.publish(RuntimeEventModel(
                        runtime_id="test",
                        event_type="runtime.started",
                    ))
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(50):
                try:
                    bus.get_recent_events(10)
                    bus.event_count
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors


# ─── 5. All Event Types Exist ──────────────────────────────


class TestEventTypes:
    def test_all_runtime_event_types(self):
        """All required runtime event types are defined."""
        required = [
            "runtime.started",
            "runtime.stopped",
            "runtime.failed",
            "runtime.recovered",
            "runtime.health_changed",
            "runtime.overloaded",
            "runtime.unavailable",
            "model.loaded",
            "model.unloaded",
            "model.switch_started",
            "model.switch_completed",
            "routing.decision",
            "routing.fallback",
            "routing.failed",
            "memory.warning",
            "vram.limit_reached",
        ]
        for t in required:
            assert t in ALL_RUNTIME_EVENT_TYPES, f"Missing event type: {t}"

    def test_event_type_enum_values(self):
        """RUNTIME_EVENT_CATEGORIES contains all types."""
        all_categorized = set()
        for cat_types in RUNTIME_EVENT_CATEGORIES.values():
            all_categorized.update(cat_types)
        assert all_categorized == set(ALL_RUNTIME_EVENT_TYPES)
