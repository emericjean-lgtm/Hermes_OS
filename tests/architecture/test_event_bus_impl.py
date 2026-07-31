"""HOS-002 sentinel tests — EventBusImpl concrete implementation."""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone

import pytest

from backend.ral import EventId, Topic, TopicPattern
from backend.ral.event_bus_impl import EventBusImpl


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


@pytest.fixture
def db_path() -> str:
    """Provide a temporary SQLite path per test case."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
async def bus(db_path: str) -> EventBusImpl:
    """Build and start a disposable EventBusImpl."""
    b = EventBusImpl(db_path, retention_days=365)
    await b.start()
    yield b
    await b.stop()


# ------------------------------------------------------------------
# 1. Lifecycle
# ------------------------------------------------------------------


async def test_start_and_stop(db_path: str) -> None:
    bus = EventBusImpl(db_path)
    assert bus._started is False
    await bus.start()
    assert bus._started is True
    await bus.stop()
    assert bus._started is False
    assert bus._stopped is True


async def test_double_start_is_idempotent(db_path: str) -> None:
    bus = EventBusImpl(db_path)
    await bus.start()
    await bus.start()  # should not raise
    assert bus._started is True
    await bus.stop()


async def test_stop_before_start_does_not_raise(db_path: str) -> None:
    bus = EventBusImpl(db_path)
    await bus.stop()  # should not raise


# ------------------------------------------------------------------
# 2. Publish
# ------------------------------------------------------------------


async def test_publish_generates_event_id(bus: EventBusImpl) -> None:
    bus.publish(Topic.RUNTIME_STARTED, {"status": "ok"})
    events = []
    async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
        events.append(e)
    assert len(events) == 1
    assert isinstance(events[0].id, str)
    assert len(events[0].id) == 32  # uuid4 hex


async def test_publish_with_publisher_and_causation(bus: EventBusImpl) -> None:
    parent_id: EventId = uuid.uuid4().hex
    bus.publish(Topic.TASK_CREATED, {"type": "parent"}, publisher="hermes_prime")
    bus.publish(
        Topic.TASK_CREATED,
        {"type": "child"},
        publisher="hermes_prime",
        causation_id=parent_id,
    )
    events = []
    async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
        events.append(e)
    assert len(events) == 2
    assert events[0].publisher == "hermes_prime"
    assert events[1].causation_id == parent_id


async def test_publish_persists_and_is_recoverable(bus: EventBusImpl) -> None:
    bus.publish(Topic.WORKFLOW_STARTED, {"wf": "test"})
    async for event in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
        assert event.topic == Topic.WORKFLOW_STARTED
        assert event.payload == {"wf": "test"}


async def test_publish_never_raises(db_path: str) -> None:
    bus = EventBusImpl(db_path)
    # Not started — publish should not crash.
    bus.publish(Topic.RUNTIME_STARTED, {"ignore": True})
    await bus.start()
    bus.publish(Topic.RUNTIME_STARTED, {"ok": True})
    await bus.stop()
    bus.publish(Topic.RUNTIME_STARTED, {"after_stop": True})  # should not crash


# ------------------------------------------------------------------
# 3. Subscribe
# ------------------------------------------------------------------


async def test_subscribe_receives_published_events(bus: EventBusImpl) -> None:
    received: list[Topic] = []
    sid = bus.subscribe(TopicPattern("*"), lambda e: received.append(e.topic))
    bus.publish(Topic.RUNTIME_STARTED, {})
    bus.publish(Topic.TASK_CREATED, {})
    bus.unsubscribe(sid)
    # Allow async dispatch to execute...
    import asyncio
    await asyncio.sleep(0.01)
    assert Topic.RUNTIME_STARTED in received
    assert Topic.TASK_CREATED in received


async def test_subscribe_pattern_filtering(bus: EventBusImpl) -> None:
    received: list[Topic] = []
    sid = bus.subscribe(TopicPattern("task.*"), lambda e: received.append(e.topic))
    bus.publish(Topic.TASK_CREATED, {})
    bus.publish(Topic.WORKFLOW_STARTED, {})  # should NOT match task.*
    bus.unsubscribe(sid)
    import asyncio
    await asyncio.sleep(0.01)
    assert Topic.TASK_CREATED in received
    assert Topic.WORKFLOW_STARTED not in received


async def test_unsubscribe_stops_receiving(bus: EventBusImpl) -> None:
    received: list[Topic] = []
    sid = bus.subscribe(TopicPattern("*"), lambda e: received.append(e.topic))
    bus.publish(Topic.RUNTIME_STARTED, {})
    bus.unsubscribe(sid)
    bus.publish(Topic.RUNTIME_STOPPED, {})
    import asyncio
    await asyncio.sleep(0.01)
    topics = {t.value for t in received}
    assert "runtime.started" in topics
    assert "runtime.stopped" not in topics


# ------------------------------------------------------------------
# 4. Replay
# ------------------------------------------------------------------


async def test_replay_since_filter(bus: EventBusImpl) -> None:
    bus.publish(Topic.RUNTIME_STARTED, {})
    import asyncio
    await asyncio.sleep(0.1)  # let timestamp advance
    cutoff = datetime.now(timezone.utc)
    bus.publish(Topic.RUNTIME_STOPPED, {})

    events = []
    async for e in bus.replay(since=cutoff):
        events.append(e)
    assert len(events) == 1
    assert events[0].topic == Topic.RUNTIME_STOPPED


async def test_replay_until_filter(bus: EventBusImpl) -> None:
    bus.publish(Topic.RUNTIME_STARTED, {})
    import asyncio
    await asyncio.sleep(0.1)
    cutoff = datetime.now(timezone.utc)
    bus.publish(Topic.RUNTIME_STOPPED, {})

    events = []
    async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc), until=cutoff):
        events.append(e)
    assert len(events) == 1
    assert events[0].topic == Topic.RUNTIME_STARTED


async def test_replay_topic_pattern(bus: EventBusImpl) -> None:
    bus.publish(Topic.TASK_CREATED, {})
    bus.publish(Topic.WORKFLOW_STARTED, {})

    events = []
    async for e in bus.replay(
        since=datetime.min.replace(tzinfo=timezone.utc),
        topic_pattern=TopicPattern("task.*"),
    ):
        events.append(e)
    assert len(events) == 1
    assert events[0].topic == Topic.TASK_CREATED


async def test_replay_empty_when_no_events(bus: EventBusImpl) -> None:
    events = []
    async for e in bus.replay(since=datetime.min.replace(tzinfo=timezone.utc)):
        events.append(e)
    assert events == []


# ------------------------------------------------------------------
# 5. Topic pattern matching (unit)
# ------------------------------------------------------------------


def test_wildcard_star_matches_any() -> None:
    from backend.ral.event_bus_impl import _topic_matches
    assert _topic_matches("*", "anything.here")


def test_wildcard_single_level() -> None:
    from backend.ral.event_bus_impl import _topic_matches
    assert _topic_matches("task.*", "task.created")
    assert not _topic_matches("task.*", "task.sub.created")
    assert not _topic_matches("task.*", "workflow.created")


def test_wildcard_recursive() -> None:
    from backend.ral.event_bus_impl import _topic_matches
    assert _topic_matches("task.**", "task.created")
    assert _topic_matches("task.**", "task.sub.created")
    assert not _topic_matches("task.**", "workflow.created")


# ------------------------------------------------------------------
# 6. Regression: HOS-000 + HOS-001 still importable
# ------------------------------------------------------------------


def test_hos_000_sds_and_capability_graph_still_importable() -> None:
    import backend.sds  # noqa: F401
    import yaml  # noqa: F401
    # capability_graph.yaml exists (tested in test_foundation_sanity)


def test_hos_001_protocols_still_importable() -> None:
    from backend.ral import (  # noqa: F401
        RuntimeInterface,
        EventBusInterface,
        ModelRouterInterface,
        Topic,
        Event,
    )
