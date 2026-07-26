"""§24.2 — the four producers actually publish, and never at their own cost.

Kronos persisting a task and Aegis queueing an approval are real work. A
dashboard notification is not. If the fan-out ever fails, the work must
still complete — this is the same rule the audit log follows, and the
reason publish() swallows everything.
"""
from __future__ import annotations

import pytest

from backend.core import event_hub
from backend.core.event_hub import EventHub, get_event_hub


@pytest.fixture
def captured(monkeypatch):
    """Record what reaches the hub, without a WebSocket in the way."""
    seen: list[tuple[str, dict]] = []
    hub = EventHub()
    monkeypatch.setattr(hub, "publish", lambda t, p: seen.append((t, p)))
    get_event_hub.cache_clear()
    monkeypatch.setattr(event_hub, "get_event_hub", lambda: hub)
    monkeypatch.setattr("backend.agents.kronos.get_event_hub", lambda: hub)
    monkeypatch.setattr("backend.security.approvals.get_event_hub", lambda: hub)
    yield seen
    get_event_hub.cache_clear()


def _types(seen):
    return [t for t, _ in seen]


# ── task.update ──────────────────────────────────────────────────────
def test_creating_a_task_announces_it(client, captured):
    client.post("/tasks", json={"title": "Écrire les tests"})

    assert "task.update" in _types(captured)
    payload = next(p for t, p in captured if t == "task.update")
    assert payload["change"] == "created"
    assert payload["title"] == "Écrire les tests"
    assert payload["status"]


def test_updating_a_task_announces_the_new_status(client, captured):
    task_id = client.post("/tasks", json={"title": "T"}).json()["id"]
    captured.clear()

    client.patch(f"/tasks/{task_id}", json={"status": "in_progress"})

    payload = next(p for t, p in captured if t == "task.update")
    assert payload["change"] == "updated"
    assert payload["status"] == "in_progress"


def test_deleting_a_task_announces_it(client, captured):
    task_id = client.post("/tasks", json={"title": "T"}).json()["id"]
    captured.clear()

    client.delete(f"/tasks/{task_id}")

    payload = next(p for t, p in captured if t == "task.update")
    assert payload["change"] == "deleted"
    assert payload["id"] == task_id


# ── validation.request ───────────────────────────────────────────────
def test_a_new_approval_is_announced(client, captured, tmp_path):
    from backend.memory.db import Base, make_engine, make_session_factory
    from backend.security import approvals

    engine = make_engine(str(tmp_path / "a.db"))
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        approvals.record_pending(
            session, action_type="file_delete", description="Delete /x",
            reason="mandatory validation",
        )

    assert "validation.request" in _types(captured)


def test_a_repeated_refusal_is_not_announced_twice(client, captured, tmp_path):
    """record_pending dedups pending rows on purpose; re-announcing would
    let an agent retrying in a loop bury the queue on the dashboard."""
    from backend.memory.db import Base, make_engine, make_session_factory
    from backend.security import approvals

    engine = make_engine(str(tmp_path / "a.db"))
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        for _ in range(3):
            approvals.record_pending(
                session, action_type="file_delete", description="Delete /x",
                reason="mandatory validation",
            )

    assert _types(captured).count("validation.request") == 1


# ── harmlessness, the load-bearing part ──────────────────────────────
def test_a_broken_hub_never_costs_a_task(client, monkeypatch):
    """The whole reason publish() wraps its own body: persisting the task
    matters, telling a dashboard about it does not.

    The failure is injected *inside* the hub rather than by replacing
    publish() — replacing the public method would bypass the very
    guarantee under test and prove nothing.
    """
    def explode(*args, **kwargs):
        raise RuntimeError("hub cassé")

    hub = EventHub()
    monkeypatch.setattr(hub, "_publish", explode)
    monkeypatch.setattr("backend.agents.kronos.get_event_hub", lambda: hub)

    response = client.post("/tasks", json={"title": "Doit survivre"})

    assert response.status_code in (200, 201)
    assert response.json()["title"] == "Doit survivre"
    assert any(t["title"] == "Doit survivre" for t in client.get("/tasks").json())
