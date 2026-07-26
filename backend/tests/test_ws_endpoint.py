"""§24.2 — the /ws channel, over the real WebSocket protocol.

TestClient's websocket_connect runs the actual ASGI handshake, so these
exercise the endpoint rather than the hub behind it (covered separately
in test_event_hub.py).
"""
from __future__ import annotations

import pytest

from backend.core.event_hub import get_event_hub


@pytest.fixture(autouse=True)
def fresh_hub():
    get_event_hub.cache_clear()
    yield
    get_event_hub.cache_clear()


def test_a_client_receives_a_published_event(client):
    with client.websocket_connect("/ws") as ws:
        get_event_hub().publish("task.update", {"id": "t1", "status": "todo"})

        frame = ws.receive_json()

    assert frame["type"] == "task.update"
    assert frame["payload"]["id"] == "t1"
    assert frame["timestamp"]


def test_a_client_can_filter(client):
    with client.websocket_connect("/ws?types=task.update") as ws:
        get_event_hub().publish("chat.token", {"text": "ignoré"})
        get_event_hub().publish("task.update", {"id": "t1"})

        frame = ws.receive_json()

    assert frame["type"] == "task.update"


def test_an_unknown_filter_is_refused_rather_than_silently_empty(client):
    """A typo'd filter would otherwise leave the client on a socket that
    never speaks — indistinguishable from a quiet system."""
    with client.websocket_connect("/ws?types=task.updat") as ws:
        frame = ws.receive_json()

    assert frame["type"] == "error"
    assert "task.updat" in frame["payload"]["detail"]
    assert "task.update" in frame["payload"]["detail"]  # names the real one


def test_disconnecting_unsubscribes(client):
    """Otherwise the hub keeps queueing for clients that left, and the
    metrics ticker never sees the room empty out."""
    with client.websocket_connect("/ws"):
        pass

    assert get_event_hub().subscriber_count == 0


def test_two_clients_both_receive(client):
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        get_event_hub().publish("agent.message", {"from": "kronos", "to": "atlas"})

        assert a.receive_json()["payload"]["from"] == "kronos"
        assert b.receive_json()["payload"]["from"] == "kronos"
