"""§24.2 — real-time fan-out.

The load-bearing property is not delivery, it is *harmlessness*: four of
the five producers are sync functions doing something that matters
(persisting a task, queueing an approval), and none of them may fail
because a dashboard is misbehaving.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.core.event_hub import EVENT_TYPES, EventHub


async def _take(hub: EventHub, n: int, *, types=None, publish=None):
    """Subscribe, publish once subscribed, collect n events."""
    collected = []
    async for event in _subscribed(hub, n, types, publish, collected):
        pass
    return collected


async def _subscribed(hub, n, types, publish, collected):
    agen = hub.subscribe(types)
    task = asyncio.create_task(_drain(agen, n, collected))
    await asyncio.sleep(0)  # let the subscription register
    if publish:
        publish()
    await asyncio.wait_for(task, timeout=2)
    return
    yield  # pragma: no cover


async def _drain(agen, n, collected):
    async for event in agen:
        collected.append(event)
        if len(collected) >= n:
            break
    await agen.aclose()


# ── the five specified types ─────────────────────────────────────────
def test_the_spec_five_are_all_supported():
    for name in ("system.metrics", "chat.token", "agent.message",
                 "task.update", "validation.request"):
        assert name in EVENT_TYPES


@pytest.mark.asyncio
async def test_a_subscriber_receives_what_is_published():
    hub = EventHub()

    events = await _take(hub, 1, publish=lambda: hub.publish("task.update", {"id": "t1"}))

    assert events[0].type == "task.update"
    assert events[0].payload == {"id": "t1"}
    assert events[0].timestamp


@pytest.mark.asyncio
async def test_every_subscriber_gets_its_own_copy():
    hub = EventHub()
    a, b = [], []
    ga, gb = hub.subscribe(), hub.subscribe()
    ta = asyncio.create_task(_drain(ga, 1, a))
    tb = asyncio.create_task(_drain(gb, 1, b))
    await asyncio.sleep(0)

    hub.publish("agent.message", {"from": "kronos"})

    await asyncio.wait_for(asyncio.gather(ta, tb), timeout=2)
    assert a[0].payload == b[0].payload == {"from": "kronos"}


@pytest.mark.asyncio
async def test_a_filtered_subscriber_gets_only_what_it_asked_for():
    hub = EventHub()

    def publish():
        hub.publish("chat.token", {"text": "ignoré"})
        hub.publish("task.update", {"id": "t1"})

    events = await _take(hub, 1, types=frozenset({"task.update"}), publish=publish)

    assert [e.type for e in events] == ["task.update"]


# ── harmlessness ─────────────────────────────────────────────────────
def test_publishing_with_nobody_listening_is_a_no_op():
    """Kronos publishes on every task change, dashboard or not."""
    EventHub().publish("task.update", {"id": "t1"})


def test_publishing_from_sync_code_without_an_event_loop_never_raises():
    """message_bus.publish, kronos.update_task and approvals.record_pending
    are plain sync functions. If publish() needed a running loop, every one
    of them would break outside the server — in the MCP tools, in a script,
    in the tests."""
    hub = EventHub()
    hub.publish("agent.message", {"from": "kronos"})  # no loop at all


def test_an_unknown_event_type_is_refused_not_broadcast():
    """A producer inventing a type would otherwise reach clients that
    cannot possibly know what to do with it."""
    hub = EventHub()
    hub.publish("task.exploded", {"id": "t1"})  # logged, not raised


@pytest.mark.asyncio
async def test_a_dead_subscriber_does_not_break_the_publisher():
    hub = EventHub()
    collected = []
    agen = hub.subscribe()
    task = asyncio.create_task(_drain(agen, 1, collected))
    await asyncio.sleep(0)
    hub.publish("task.update", {"id": "t1"})
    await asyncio.wait_for(task, timeout=2)

    # The consumer is gone; publishing must stay harmless.
    hub.publish("task.update", {"id": "t2"})
    assert hub.subscriber_count == 0


# ── backpressure is announced, never silent ──────────────────────────
@pytest.mark.asyncio
async def test_a_slow_client_drops_the_oldest_and_is_told():
    """A stream that silently skips events is worse than one admitting a
    gap: the reader has no way to know the picture is incomplete."""
    hub = EventHub(queue_size=4)
    collected = []
    agen = hub.subscribe()
    task = asyncio.create_task(_drain(agen, 5, collected))
    await asyncio.sleep(0)

    for i in range(10):  # more than the queue holds, consumer not running
        hub.publish("chat.token", {"i": i})
    await asyncio.wait_for(task, timeout=2)

    kinds = [e.type for e in collected]
    assert "stream.dropped" in kinds
    dropped = next(e for e in collected if e.type == "stream.dropped")
    assert dropped.payload["count"] > 0
    # Newest kept, oldest discarded.
    tokens = [e.payload["i"] for e in collected if e.type == "chat.token"]
    assert max(tokens) >= 6


@pytest.mark.asyncio
async def test_a_slow_client_never_slows_the_publisher():
    """publish() must not block on a full queue — the caller is streaming
    an answer to a human."""
    hub = EventHub(queue_size=2)
    collected = []
    agen = hub.subscribe()
    task = asyncio.create_task(_drain(agen, 1, collected))
    await asyncio.sleep(0)

    for i in range(500):
        hub.publish("chat.token", {"i": i})  # returns immediately, always

    await asyncio.wait_for(task, timeout=2)
