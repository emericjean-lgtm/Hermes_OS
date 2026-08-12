"""memory_remember -> memory_search must actually find it (HOS-086).

Reported symptom: ``memory_remember`` returned an id and ``memory_search``
returned ``[]`` for the very same text, every time. Root cause was not a
retrieval-quality problem — the two MCP tools addressed different stores.
``memory_remember`` wrote a ``MemoryEntry`` row through
``episodic.add_memory``; ``memory_search`` called ``EchoAgent.recall``,
which queries the *document* vector index. Nothing ever wrote a remembered
fact into that index, so the search could not have succeeded.

These tests assert the round trip a caller actually expects, and the
cross-session survival that makes it memory rather than a cache. An id in
the ``memory_remember`` response is explicitly not accepted as evidence.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def echo(monkeypatch, tmp_path):
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "memory.db"))
    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    agent = get_agent_registry().get("echo")
    yield agent
    get_settings.cache_clear()
    get_agent_registry.cache_clear()


def test_remembered_fact_is_findable(echo):
    echo.remember(
        type_="fact",
        content="The Hermes OS backend listens on port 8010.",
        tags=["deployment"],
    )

    hits = echo.search_memories("port 8010")

    assert hits, "a fact stored seconds ago was not retrievable"
    assert "8010" in hits[0]["content"]
    assert hits[0]["source"] == "memory"


def test_search_is_scoped_by_project(echo):
    echo.remember(type_="fact", content="Alpha uses PostgreSQL.", project_id="proj-a")
    echo.remember(type_="fact", content="Beta uses SQLite.", project_id="proj-b")

    hits = echo.search_memories("uses", project_id="proj-a")

    assert len(hits) == 1
    assert "Alpha" in hits[0]["content"]


def test_best_match_ranks_first(echo):
    echo.remember(type_="fact", content="Ollama serves models locally.")
    echo.remember(type_="fact", content="The agentic model floor is devstral.")

    hits = echo.search_memories("agentic model floor")

    assert "devstral" in hits[0]["content"], "incidental one-word overlap outranked the real match"


def test_memory_survives_a_restart(monkeypatch, tmp_path):
    """Session A remembers, the process-wide registry is torn down, session B
    finds it. A store that only answers within one session is a cache."""
    from backend.core.agent_registry import get_agent_registry
    from backend.core.config import get_settings

    db = tmp_path / "persist.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))

    get_settings.cache_clear()
    get_agent_registry.cache_clear()
    get_agent_registry().get("echo").remember(
        type_="fact", content="Skill360 workspace lives under C:/Users/emeri.",
    )

    # Session B — nothing of session A survives except the database itself.
    get_settings.cache_clear()
    get_agent_registry.cache_clear()

    hits = get_agent_registry().get("echo").search_memories("Skill360 workspace")

    assert hits, "memory did not survive the restart"
    assert "Skill360" in hits[0]["content"]

    get_settings.cache_clear()
    get_agent_registry.cache_clear()


def test_memory_search_answers_without_the_document_index(echo, monkeypatch):
    """Document search needs live embeddings; remembered facts do not. A
    down Ollama must not turn a retrievable fact into an empty result."""
    from backend.mcp_server import server

    echo.remember(type_="fact", content="The agentic fallback model is devstral.")
    monkeypatch.setattr(server, "_echo", lambda: echo)
    monkeypatch.setattr(
        type(echo), "recall",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("embeddings unavailable")),
    )

    hits = server.memory_search("agentic fallback")

    assert hits, "memory_search returned nothing because the document index was down"
    assert "devstral" in hits[0]["content"]
