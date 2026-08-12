"""UnifiedMemory must survive the process (HOS-098).

``UnifiedMemory`` is the facade every scope goes through — session, mission,
agent, project, user, global, experience — and it was designed with a
pluggable ``MemoryBackend`` so the store could be swapped for something
durable later. Later never came: ``InMemoryBackend``, a plain dict, was the
only implementation, and ``mission_control``, ``hos_routes`` and the Hermes
Agent adapter had all been writing to it. Everything they remembered died
with the process.

That left the system with two memories holding opposite guarantees:
``episodic.py`` persists to SQLite and answers memory_remember/memory_search,
while the facade the agent integration uses persisted nothing.

These tests assert the property that was missing, the same way the episodic
round-trip tests do: write, discard everything holding state, read again.
An id returned by ``store`` is not accepted as evidence of persistence.
"""
from __future__ import annotations

import pytest

from backend.memory.unified_memory import (
    MemoryQuery,
    MemoryScope,
    UnifiedMemory,
)
from backend.memory.unified_sqlite_backend import SqliteMemoryBackend


@pytest.fixture
def db(monkeypatch, tmp_path):
    from backend.core.config import get_settings

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "unified.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _memory() -> UnifiedMemory:
    """A facade over a freshly constructed backend — nothing carried over."""
    return UnifiedMemory(backend=SqliteMemoryBackend())


def test_an_entry_survives_a_restart(db):
    written = _memory().store(
        scope=MemoryScope.MISSION, title="Port",
        content="Backend listens on 8010", tags={"deploy"}, importance=7,
    )

    # Nothing of the previous instance survives except the database file.
    recovered = _memory().get(written.id)

    assert recovered is not None, "the entry did not survive the restart"
    assert recovered.content == "Backend listens on 8010"


def test_every_field_survives_not_just_the_content(db):
    """Tags, importance and metadata are what the query filters run on; a
    round trip that loses them persists the text and breaks the search."""
    written = _memory().store(
        scope=MemoryScope.PROJECT, title="t", content="c",
        tags={"alpha", "beta"}, importance=9, metadata={"project_id": "p1"},
    )

    recovered = _memory().get(written.id)

    assert sorted(recovered.tags) == ["alpha", "beta"]
    assert recovered.importance == 9
    assert recovered.metadata == {"project_id": "p1"}
    assert recovered.created_at == written.created_at


def test_queries_still_work_after_a_restart(db):
    memory = _memory()
    memory.store(scope=MemoryScope.MISSION, title="Port",
                 content="listens on 8010", tags={"deploy"}, importance=7)
    memory.store(scope=MemoryScope.PROJECT, title="Autre",
                 content="unrelated", tags={"x"}, importance=2)

    after = _memory()

    assert [e.title for e in after.search(
        MemoryQuery(scope=MemoryScope.MISSION, text="8010")).entries] == ["Port"]
    assert [e.title for e in after.search(
        MemoryQuery(tags=frozenset({"deploy"}))).entries] == ["Port"]
    assert [e.title for e in after.search(
        MemoryQuery(min_importance=5)).entries] == ["Port"]


def test_scopes_stay_isolated_after_a_restart(db):
    memory = _memory()
    memory.store(scope=MemoryScope.MISSION, title="mine", content="c")
    memory.store(scope=MemoryScope.PROJECT, title="theirs", content="c")

    after = _memory()

    assert [e.title for e in after.search(
        MemoryQuery(scope=MemoryScope.PROJECT)).entries] == ["theirs"]
    assert after.get_statistics().per_scope == {"mission": 1, "project": 1}


def test_an_update_is_persisted_not_duplicated(db):
    written = _memory().store(scope=MemoryScope.GLOBAL, title="v1", content="first")

    _memory().update(written.id, content="second")
    after = _memory()

    assert after.get(written.id).content == "second"
    assert after.get_statistics().total_entries == 1


def test_a_deletion_is_persisted(db):
    """A memory that comes back after being deleted is worse than one that
    never persisted."""
    written = _memory().store(scope=MemoryScope.GLOBAL, title="t", content="c")

    assert _memory().delete(written.id) is True
    assert _memory().get(written.id) is None


def test_clear_scope_leaves_other_scopes_alone(db):
    memory = _memory()
    memory.store(scope=MemoryScope.SESSION, title="s1", content="c")
    memory.store(scope=MemoryScope.SESSION, title="s2", content="c")
    memory.store(scope=MemoryScope.GLOBAL, title="g1", content="c")

    assert _memory().clear_scope(MemoryScope.SESSION) == 2

    after = _memory()
    assert after.get_statistics().total_entries == 1
    assert [e.title for e in after.search(MemoryQuery()).entries] == ["g1"]


def test_pagination_is_applied_after_filtering(db):
    """Tags live in a JSON column and are filtered in Python; applying the
    limit before that filter would silently return fewer rows than asked."""
    memory = _memory()
    for i in range(5):
        memory.store(scope=MemoryScope.GLOBAL, title=f"t{i}", content="c",
                     tags={"keep"} if i % 2 == 0 else {"drop"})

    result = _memory().search(MemoryQuery(tags=frozenset({"keep"}), limit=2))

    assert len(result.entries) == 2
    assert all("keep" in e.tags for e in result.entries)
