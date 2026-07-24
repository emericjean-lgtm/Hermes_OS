from __future__ import annotations

from backend.agents.echo import EchoAgent

# retrieve() goes through EchoAgent.recall(), which needs a live Ollama
# server for embeddings — patched at the class level here (affects every
# EchoAgent instance, including the one MinervaAgent.retrieve() reaches
# via the *global* get_agent_registry(), separate from the `client`
# fixture's local fake-Ollama-backed registry — see conftest.py's client
# fixture docstring for why Minerva needs that extra isolation).

_FAKE_PASSAGES = [
    {"id": "doc-0", "content": "Hermes Ollama targets an RX 6800.", "metadata": {"source": "readme.md"}, "distance": 0.1},
]


def test_research_returns_answer_and_passages(client, monkeypatch):
    monkeypatch.setattr(
        EchoAgent, "recall", lambda self, query, n_results=5: _FAKE_PASSAGES
    )

    response = client.post("/research", json={"query": "What GPU does it target?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Hello, world!"  # fake Ollama client's canned response
    assert body["passages"] == _FAKE_PASSAGES
    assert body["model"]
    assert body["tier"]


def test_research_with_no_matching_passages(client, monkeypatch):
    monkeypatch.setattr(EchoAgent, "recall", lambda self, query, n_results=5: [])

    response = client.post("/research", json={"query": "anything?"})

    assert response.status_code == 200
    assert response.json()["passages"] == []
