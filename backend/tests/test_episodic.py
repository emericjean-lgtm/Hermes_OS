from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from backend.memory import episodic
from backend.memory.db import init_db, make_session_factory


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


def test_add_memory_persists_and_dates_automatically(session):
    entry = episodic.add_memory(session, type_="preference", content="dark mode please")
    assert entry.id
    assert entry.content == "dark mode please"
    assert entry.created_at is not None


def test_add_memory_deduplicates_exact_content_within_same_type(session):
    first = episodic.add_memory(session, type_="preference", content="dark mode please")
    second = episodic.add_memory(session, type_="preference", content="dark mode please")
    assert first.id == second.id
    assert len(episodic.list_memories(session, type_="preference")) == 1


def test_add_memory_same_content_different_type_is_not_deduplicated(session):
    episodic.add_memory(session, type_="preference", content="same text")
    episodic.add_memory(session, type_="decision", content="same text")
    assert len(episodic.list_memories(session)) == 2


def test_list_memories_filters_by_type(session):
    episodic.add_memory(session, type_="preference", content="a")
    episodic.add_memory(session, type_="decision", content="b")
    assert [e.content for e in episodic.list_memories(session, type_="decision")] == ["b"]


def test_list_memories_orders_most_recent_first(session):
    episodic.add_memory(session, type_="preference", content="first")
    episodic.add_memory(session, type_="preference", content="second")
    contents = [e.content for e in episodic.list_memories(session)]
    assert contents == ["second", "first"]


def test_get_memory_returns_none_for_unknown_id(session):
    assert episodic.get_memory(session, "does-not-exist") is None


def test_delete_memory_removes_entry_and_returns_true(session):
    entry = episodic.add_memory(session, type_="preference", content="to be deleted")
    assert episodic.delete_memory(session, entry.id) is True
    assert episodic.get_memory(session, entry.id) is None


def test_delete_memory_returns_false_for_unknown_id(session):
    assert episodic.delete_memory(session, "does-not-exist") is False


def test_memory_entry_stores_tags_and_confidence(session):
    entry = episodic.add_memory(
        session, type_="decision", content="use qwen3-coder for code", tags=["models", "routing"], confidence=0.8
    )
    assert entry.tags == "models,routing"
    assert entry.confidence == 0.8
