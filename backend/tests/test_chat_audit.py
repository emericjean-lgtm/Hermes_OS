"""§18 — /chat writes exactly one audit record, and never at the user's expense.

The instrumentation is what makes §22.1's latency budgets (T1/T3/T5)
measurable at all, so these tests pin the measurement itself, not just
that a row appeared.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core import audit_log
from backend.core.config import get_settings
from backend.main import create_app
from backend.memory.db import make_engine, make_session_factory


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "hermes.db"))
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _records():
    with make_session_factory(make_engine(get_settings().sqlite_path))() as s:
        return audit_log.list_records(s)


def test_a_chat_leaves_one_record_with_its_routing(client):
    body = {"messages": [{"role": "user", "content": "bonjour"}],
            "agent": "hermes_prime", "session_id": "sess-42"}

    response = client.post("/chat", json=body)
    assert response.status_code == 200
    _ = response.text  # the stream must be drained before the record exists

    records = _records()
    assert len(records) == 1
    assert records[0].session_id == "sess-42"
    assert records[0].agent == "hermes_prime"
    assert "model_selected" in records[0].routing_decision


def test_the_measurement_is_real(client):
    """A record whose duration is null would satisfy "a row appeared" while
    leaving §22.1 exactly as unverifiable as before."""
    client.post("/chat", json={"messages": [{"role": "user", "content": "salut"}]}).text

    stored = _records()[0]
    assert stored.duration_ms is not None
    assert stored.tokens_used is not None and stored.tokens_used > 0
    assert stored.tokens_per_second is not None


def test_the_request_is_scrubbed_before_it_is_stored(client):
    client.post("/chat", json={"messages": [
        {"role": "user", "content": "déploie avec API_KEY=sk-supersecret0123456789"}
    ]}).text

    assert "sk-supersecret0123456789" not in _records()[0].request


def test_a_broken_audit_log_never_costs_the_user_their_answer(client, monkeypatch):
    """Observability is not worth a 500 in the middle of a response."""
    def explode(*args, **kwargs):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(audit_log, "record", explode)

    response = client.post("/chat", json={"messages": [{"role": "user", "content": "salut"}]})

    assert response.status_code == 200
    assert response.text  # tokens still delivered
    assert _records() == []


def test_latency_stats_see_the_chat(client):
    """The end-to-end point of §18: /logs/latency answers from real traffic."""
    client.post("/chat", json={"messages": [{"role": "user", "content": "salut"}]}).text

    stats = client.get("/logs/latency").json()
    assert stats["samples"] == 1
    assert stats["duration_ms"]["median"] is not None


def test_an_answer_with_no_tokens_is_not_recorded_as_success(client, monkeypatch):
    """Observed on real hardware: a 59s turn, zero content tokens, logged
    as "success". A reasoning model can spend the whole turn in its
    thinking channel, which chat_stream does not yield. Calling that a
    success is how a broken path stays invisible in the logs."""
    from backend.core.agent_registry import get_agent_registry

    async def nothing():
        return
        yield  # pragma: no cover - makes this an async generator

    agent = get_agent_registry().get("hermes_prime")
    original = agent.respond

    async def silent(*args, **kwargs):
        decision, _ = await original(*args, **kwargs)
        return decision, nothing()

    monkeypatch.setattr(agent, "respond", silent)

    assert client.post("/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 200

    stored = _records()[0]
    assert stored.result == "empty"
    assert stored.tokens_used == 0
    assert "no content token" in stored.error
