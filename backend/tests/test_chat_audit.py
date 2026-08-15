"""§18 — /chat writes exactly one audit record, and never at the user's expense.

The instrumentation is what makes §22.1's latency budgets (T1/T3/T5)
measurable at all, so these tests pin the measurement itself, not just
that a row appeared.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.connectors.ollama_client import OllamaClient, StreamChunk
from backend.core import audit_log
from backend.core.agent_registry import get_agent_registry
from backend.core.config import get_settings
from backend.main import create_app
from backend.core.router import RoutingDecision
from backend.memory.db import make_engine, make_session_factory

_REPONSE = ("Hello", ", ", "world", "!")

#: Sur Windows, `time.monotonic()` avance par pas d'environ 15,6 ms.
#: Une doublure instantanée livre ses quatre morceaux dans le même pas :
#: `Timer.tokens_per_second` mesure alors un `elapsed` nul et rend `None`
#: — à juste titre, il refuse de diviser par zéro. Le test qui vérifie que
#: la mesure est réelle échouait donc sur la doublure, pas sur le code.
#: 20 ms tient au-dessus de la granularité avec de la marge ; plus court
#: rendrait ce test intermittent, ce qui serait pire que faux.
_PAS_MS = 0.020


async def _chat_events_inerte(self, model, messages, **kwargs):
    for text in _REPONSE:
        yield StreamChunk("content", text)
        await asyncio.sleep(_PAS_MS)


async def _chat_stream_inerte(self, model, messages, **kwargs):
    async for chunk in _chat_events_inerte(self, model, messages, **kwargs):
        if chunk.kind == "content":
            yield chunk.text


async def _aucun_modele_resident(self):
    """Le routeur demande qui est déjà chargé avant de choisir (§10.3).

    Neutraliser le seul `chat_*` ne suffisait pas : cet appel-là ouvrait
    encore une vraie connexion, mise en pool sur la boucle d'événements du
    premier test, et le test suivant mourait dessus en
    « Event loop is closed » — pas au moment de la faute, mais un test
    plus loin.
    """
    return []


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Aucun appel réseau — la doublure est posée sur la *classe*.

    Ce fixture porte le même nom que celui de `conftest.py`, qui injecte
    `FakeOllamaClient` et documente sur quarante lignes qu'aucun agent ne
    doit toucher au réseau. Le nom identique le masquait : chaque
    `POST /chat` de ce fichier partait vers un vrai Ollama. Quand le
    serveur mettait un modèle à charger, le test ne ralentissait pas — il
    pendait, sans limite. Deux exécutions de la suite s'y sont figées, 92
    et 15 minutes, sans jamais rendre de verdict (HOS-112).

    La doublure est posée au niveau de la classe, et non sur le registre
    de la route, parce que `test_an_answer_with_no_tokens_is_not_recorded_
    as_success` appelle `get_agent_registry()` directement : un registre
    injecté dans le seul module de route laisserait ce test-là parler au
    réseau. Patcher la classe rend inerte tout client, quel que soit le
    registre qui le détient — c'est le motif que le docstring de
    `conftest.py` désigne déjà pour ce cas.
    """
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "hermes.db"))
    monkeypatch.setattr(OllamaClient, "chat_events", _chat_events_inerte)
    monkeypatch.setattr(OllamaClient, "chat_stream", _chat_stream_inerte)
    monkeypatch.setattr(OllamaClient, "list_running_models", _aucun_modele_resident)
    monkeypatch.setattr(OllamaClient, "list_local_models", _aucun_modele_resident)
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()
    get_agent_registry.cache_clear()


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
    decision = RoutingDecision(
        task_type="conversation", role="standard", model="fake:1b",
        tier="standard", reason="fixture", thinking=False,
    )

    async def silent(*args, **kwargs):
        # No network at all. An earlier version called the real
        # respond_events for its decision: that opened a connection to
        # Ollama which stayed pooled against this test's event loop, and
        # the *next* test died on "Event loop is closed" reusing it. This
        # test is about the record, not about routing.
        return decision, nothing()

    monkeypatch.setattr(agent, "respond_events", silent)

    assert client.post("/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 200

    stored = _records()[0]
    assert stored.result == "empty"
    assert stored.tokens_used == 0
    assert "no content token" in stored.error


def test_the_default_body_is_unchanged_raw_content(client):
    """Load-bearing default: the existing frontend and every non-opting
    consumer must keep receiving raw text, byte for byte."""
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "x"}]})

    assert response.headers["content-type"].startswith("text/plain")
    assert not response.text.lstrip().startswith("{")


def test_opting_in_switches_to_ndjson(client):
    response = client.post("/chat", json={
        "messages": [{"role": "user", "content": "x"}], "include_thinking": True,
    })

    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert lines, "aucune ligne NDJSON"
    assert all(set(line) == {"kind", "text"} for line in lines)
    assert all(line["kind"] in ("thinking", "content") for line in lines)


def test_the_client_is_told_whether_reasoning_is_on(client):
    """So it can render a reasoning panel without re-deriving the routing
    rule it does not own."""
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "x"}]})

    assert response.headers["X-Hermes-Thinking"] in ("true", "false")
