"""HOS-021 sentinel tests — Unified Memory Intelligence Layer.

Tests storage, search, filtering, scopes, import/export, statistics and
thread safety without any external dependency.
"""

from __future__ import annotations

import json
import threading

import pytest

from backend.memory.unified_memory import (
    InMemoryBackend,
    MemoryEntry,
    MemoryEvent,
    MemoryQuery,
    MemoryResult,
    MemoryScope,
    MemoryStatistics,
    UnifiedMemory,
    UnifiedMemoryError,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_memory_scope_values() -> None:
    assert MemoryScope.SESSION.value == "session"
    assert MemoryScope.MISSION.value == "mission"
    assert MemoryScope.AGENT.value == "agent"
    assert MemoryScope.PROJECT.value == "project"
    assert MemoryScope.USER.value == "user"
    assert MemoryScope.GLOBAL.value == "global"
    assert MemoryScope.EXPERIENCE.value == "experience"


def test_memory_entry_defaults() -> None:
    entry = MemoryEntry(id="e1", scope=MemoryScope.SESSION)
    assert entry.id == "e1"
    assert entry.title == ""
    assert entry.content == ""
    assert entry.tags == frozenset()
    assert entry.importance == 1
    assert entry.created_at > 0


def test_memory_entry_frozen() -> None:
    entry = MemoryEntry(id="e1", scope=MemoryScope.SESSION)
    with pytest.raises(AttributeError):
        entry.id = "e2"  # type: ignore[misc]


def test_memory_query_defaults() -> None:
    q = MemoryQuery()
    assert q.scope is None
    assert q.text is None
    assert q.limit is None
    assert q.offset == 0


def test_memory_result_defaults() -> None:
    r = MemoryResult()
    assert r.entries == ()
    assert r.total == 0
    assert r.execution_time_ms == 0.0


def test_memory_statistics_defaults() -> None:
    s = MemoryStatistics()
    assert s.total_entries == 0
    assert s.per_scope == {}
    assert s.total_searches == 0


def test_memory_event_values() -> None:
    assert MemoryEvent.STORED.value == "memory.stored"
    assert MemoryEvent.UPDATED.value == "memory.updated"
    assert MemoryEvent.DELETED.value == "memory.deleted"
    assert MemoryEvent.IMPORTED.value == "memory.imported"
    assert MemoryEvent.EXPORTED.value == "memory.exported"


# ============================================================================
# InMemoryBackend
# ============================================================================


def test_backend_store_and_get() -> None:
    backend = InMemoryBackend()
    entry = MemoryEntry(id="e1", scope=MemoryScope.SESSION, content="hello")
    backend.store(entry)
    retrieved = backend.get("e1")
    assert retrieved is not None
    assert retrieved.content == "hello"


def test_backend_get_missing() -> None:
    backend = InMemoryBackend()
    assert backend.get("nonexistent") is None


def test_backend_delete_existing() -> None:
    backend = InMemoryBackend()
    backend.store(MemoryEntry(id="e1", scope=MemoryScope.SESSION))
    assert backend.delete("e1") is True
    assert backend.get("e1") is None


def test_backend_delete_missing() -> None:
    backend = InMemoryBackend()
    assert backend.delete("nonexistent") is False


# ============================================================================
# UnifiedMemory: store / get / update / delete
# ============================================================================


def test_store_and_get() -> None:
    mem = UnifiedMemory()
    entry = mem.store("Hello world", scope=MemoryScope.SESSION)
    assert entry.id is not None
    assert entry.content == "Hello world"
    assert entry.scope == MemoryScope.SESSION

    retrieved = mem.get(entry.id)
    assert retrieved is not None
    assert retrieved.content == "Hello world"


def test_store_with_custom_id() -> None:
    mem = UnifiedMemory()
    entry = mem.store("data", entry_id="custom1")
    assert entry.id == "custom1"


def test_get_missing() -> None:
    mem = UnifiedMemory()
    assert mem.get("nonexistent") is None


def test_update_entry() -> None:
    mem = UnifiedMemory()
    entry = mem.store("old content", title="Old")
    updated = mem.update(entry.id, content="new content", title="New")
    assert updated.content == "new content"
    assert updated.title == "New"


def test_update_nonexistent_raises() -> None:
    mem = UnifiedMemory()
    with pytest.raises(UnifiedMemoryError, match="not found"):
        mem.update("nonexistent", content="x")


def test_delete_entry() -> None:
    mem = UnifiedMemory()
    entry = mem.store("to delete")
    assert mem.delete(entry.id) is True
    assert mem.get(entry.id) is None


def test_delete_missing() -> None:
    mem = UnifiedMemory()
    assert mem.delete("nonexistent") is False


# ============================================================================
# Search
# ============================================================================


def test_search_all() -> None:
    mem = UnifiedMemory()
    mem.store("A", scope=MemoryScope.SESSION)
    mem.store("B", scope=MemoryScope.MISSION)
    result = mem.search(MemoryQuery())
    assert result.total == 2
    assert len(result.entries) == 2


def test_search_by_scope() -> None:
    mem = UnifiedMemory()
    mem.store("A", scope=MemoryScope.SESSION)
    mem.store("B", scope=MemoryScope.MISSION)
    result = mem.search(MemoryQuery(scope=MemoryScope.SESSION))
    assert result.total == 1
    assert result.entries[0].content == "A"


def test_search_by_text() -> None:
    mem = UnifiedMemory()
    mem.store("Hello world", title="Greeting")
    mem.store("Goodbye world", title="Farewell")
    result = mem.search(MemoryQuery(text="hello"))
    assert result.total == 1


def test_search_by_tags() -> None:
    mem = UnifiedMemory()
    mem.store("A", tags=frozenset({"important", "urgent"}))
    mem.store("B", tags=frozenset({"normal"}))
    result = mem.search(MemoryQuery(tags=frozenset({"important"})))
    assert result.total == 1


def test_search_by_importance() -> None:
    mem = UnifiedMemory()
    mem.store("A", importance=8)
    mem.store("B", importance=3)
    result = mem.search(MemoryQuery(min_importance=5))
    assert result.total == 1


def test_search_pagination() -> None:
    mem = UnifiedMemory()
    for i in range(10):
        mem.store(f"Entry {i}")
    result = mem.search(MemoryQuery(limit=3, offset=0))
    assert len(result.entries) == 3
    assert result.total == 10


# ============================================================================
# Scopes
# ============================================================================


def test_clear_scope() -> None:
    mem = UnifiedMemory()
    mem.store("A", scope=MemoryScope.SESSION)
    mem.store("B", scope=MemoryScope.MISSION)
    removed = mem.clear_scope(MemoryScope.SESSION)
    assert removed == 1
    assert mem.get_statistics().total_entries == 1


# ============================================================================
# Import / Export
# ============================================================================


def test_export_and_import() -> None:
    mem = UnifiedMemory()
    mem.store("Content A", title="Title A", scope=MemoryScope.MISSION, importance=5)
    mem.store("Content B", title="Title B", scope=MemoryScope.SESSION)

    exported = mem.export(indent=2)
    data = json.loads(exported)
    assert len(data) == 2

    # Import into a new memory store.
    mem2 = UnifiedMemory()
    count = mem2.import_json(exported)
    assert count == 2
    assert mem2.get_statistics().total_entries == 2


def test_export_filtered_by_scope() -> None:
    mem = UnifiedMemory()
    mem.store("A", scope=MemoryScope.SESSION)
    mem.store("B", scope=MemoryScope.MISSION)
    exported = mem.export(scope=MemoryScope.SESSION)
    data = json.loads(exported)
    assert len(data) == 1


# ============================================================================
# Statistics
# ============================================================================


def test_statistics_after_operations() -> None:
    mem = UnifiedMemory()
    mem.store("A", scope=MemoryScope.SESSION)
    mem.store("B", scope=MemoryScope.MISSION)
    mem.search(MemoryQuery())
    mem.search(MemoryQuery(text="A"))

    stats = mem.get_statistics()
    assert stats.total_entries == 2
    assert stats.total_searches == 2
    assert "session" in stats.per_scope
    assert stats.per_scope["session"] == 1


# ============================================================================
# Events
# ============================================================================


def test_event_on_store() -> None:
    mem = UnifiedMemory()
    events: list[tuple[MemoryEvent, str]] = []
    mem.on_event(lambda evt, entry: events.append((evt, entry.id)))

    entry = mem.store("test")
    assert len(events) == 1
    assert events[0][0] == MemoryEvent.STORED
    assert events[0][1] == entry.id


def test_event_on_update() -> None:
    mem = UnifiedMemory()
    events: list[MemoryEvent] = []
    mem.on_event(lambda evt, entry: events.append(evt))

    entry = mem.store("original")
    mem.update(entry.id, content="updated")
    assert MemoryEvent.UPDATED in events


def test_event_on_delete() -> None:
    mem = UnifiedMemory()
    events: list[MemoryEvent] = []
    mem.on_event(lambda evt, entry: events.append(evt))

    entry = mem.store("to delete")
    mem.delete(entry.id)
    assert MemoryEvent.DELETED in events


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_store_and_search() -> None:
    mem = UnifiedMemory()

    def writer(n: int) -> None:
        for i in range(50):
            mem.store(f"data_{n}_{i}", scope=MemoryScope.SESSION)

    def searcher() -> None:
        for _ in range(50):
            mem.search(MemoryQuery())

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(3)]
    threads.append(threading.Thread(target=searcher))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = mem.get_statistics()
    assert stats.total_entries == 150


def test_concurrent_import_and_search() -> None:
    mem = UnifiedMemory()
    data = json.dumps([
        {"id": f"e{i}", "scope": "session", "content": f"data{i}"}
        for i in range(50)
    ])

    errors: list[Exception] = []

    def importer() -> None:
        for _ in range(10):
            try:
                mem.import_json(data)
            except Exception as e:
                errors.append(e)

    def searcher() -> None:
        for _ in range(30):
            try:
                mem.search(MemoryQuery())
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=importer)
    t2 = threading.Thread(target=searcher)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
