"""Conversations survive the process that had them (HOS-101).

``ConversationManager`` kept every transcript in a dict behind a 100-session
LRU. Restarting the backend erased the lot, and the 101st conversation
deleted the first outright — the same class of gap HOS-098 closed for
UnifiedMemory, on the surface the user actually looks at.

The load-bearing test here is ``test_a_conversation_survives_a_restart``:
it builds a *second* manager over the same database, which is what a
restart really is. Everything else guards a way that could quietly stop
being true — duplicated messages, reordered turns, an eviction that still
destroys.
"""
from __future__ import annotations

import pytest

from backend.conversation.conversation_manager import ConversationManager
from backend.conversation.conversation_models import MessageRole
from backend.conversation.conversation_store import SqliteConversationStore
from backend.memory.db import init_db, make_engine, make_session_factory


@pytest.fixture
def db(tmp_path):
    """A real SQLite file, shared by every manager a test builds."""
    engine = make_engine(str(tmp_path / "conversations.db"))
    init_db(engine)
    return make_session_factory(engine)


@pytest.fixture
def manager(db):
    return ConversationManager(store=SqliteConversationStore(db))


def _restart(db) -> ConversationManager:
    """What a backend restart amounts to: a new manager, the same disk."""
    return ConversationManager(store=SqliteConversationStore(db))


# ── the point of the exercise ────────────────────────────────────────────

def test_a_conversation_survives_a_restart(manager, db):
    session = manager.create_session(user_id="emeric")
    manager.begin_stream(session.session_id, "Quel modèle pour les missions ?")
    manager.finish_stream(session.session_id, "LFM2.5-2.6B, mesuré 3/3.")

    restored = _restart(db).get_session(session.session_id)

    assert restored is not None, "the session did not survive the restart"
    assert [m.content for m in restored.messages] == [
        "Quel modèle pour les missions ?",
        "LFM2.5-2.6B, mesuré 3/3.",
    ]
    assert restored.user_id == "emeric"


def test_the_history_endpoint_reads_a_restored_conversation(manager, db):
    """get_history goes through get_session, so rehydration has to reach it
    — this is the call the Assistant tab actually makes."""
    session = manager.create_session()
    manager.begin_stream(session.session_id, "salut")
    manager.finish_stream(session.session_id, "bonjour")

    history = _restart(db).get_history(session.session_id)

    assert [h["role"] for h in history] == [MessageRole.USER.value, MessageRole.HERMES.value]
    assert history[0]["content"] == "salut"


def test_past_conversations_are_listed_after_a_restart(manager, db):
    first = manager.create_session()
    manager.begin_stream(first.session_id, "première question")
    manager.finish_stream(first.session_id, "réponse")
    second = manager.create_session()
    manager.begin_stream(second.session_id, "deuxième question")
    manager.finish_stream(second.session_id, "réponse")

    listed = _restart(db).list_sessions()

    ids = {row["session_id"] for row in listed}
    assert {first.session_id, second.session_id} <= ids


# ── retrieval: a list of ids is not a list a human can use ──────────────

def test_a_session_is_titled_by_its_first_question(manager):
    session = manager.create_session()
    manager.begin_stream(session.session_id, "Comment lancer une mission ?")
    manager.finish_stream(session.session_id, "Par le Mission Center.")

    row = next(r for r in manager.list_sessions()
               if r["session_id"] == session.session_id)

    assert row["title"] == "Comment lancer une mission ?"
    assert row["message_count"] == 2


def test_a_long_question_is_truncated_rather_than_wrapped(manager):
    session = manager.create_session()
    manager.begin_stream(session.session_id, "détaille " * 40)
    manager.finish_stream(session.session_id, "ok")

    title = manager.list_sessions()[0]["title"]

    assert len(title) <= 80
    assert title.endswith("…")


def test_the_title_ignores_the_assistants_own_words(manager):
    """A title taken from the reply would describe what the model said, not
    what the user wanted — useless for finding a conversation again."""
    session = manager.create_session()
    manager.finish_stream(session.session_id, "Je suis Hermes.")
    manager.begin_stream(session.session_id, "qui es-tu ?")

    assert manager.list_sessions()[0]["title"] == "qui es-tu ?"


# ── the ways persistence goes wrong quietly ─────────────────────────────

def test_messages_are_not_duplicated_by_repeated_saves(manager, db):
    """Every mutation persists, and several happen per turn. If sync wrote
    the whole transcript each time, a two-line conversation would come back
    with six lines."""
    session = manager.create_session()
    manager.begin_stream(session.session_id, "un")
    manager.finish_stream(session.session_id, "deux")
    manager.set_project(session.session_id, None)
    manager.set_project(session.session_id, None)

    restored = _restart(db).get_session(session.session_id)

    assert [m.content for m in restored.messages] == ["un", "deux"]


def test_turn_order_survives_a_shared_timestamp(manager, db):
    """A question and its answer can land in the same millisecond. Ordering
    by timestamp would then be a coin toss; the stored sequence is not."""
    session = manager.create_session()
    for index in range(6):
        manager.begin_stream(session.session_id, f"q{index}")
        manager.finish_stream(session.session_id, f"a{index}")
    for message in session.messages:      # collapse every clock reading
        message.timestamp = "2026-08-13T10:00:00+00:00"
    manager._persist(session)             # noqa: SLF001

    restored = _restart(db).get_session(session.session_id)

    assert [m.content for m in restored.messages] == [
        c for index in range(6) for c in (f"q{index}", f"a{index}")
    ]


def test_the_bound_workspace_survives_a_restart(manager, db):
    """The session's Project binding is what gates filesystem tools. Losing
    it on restart would silently disarm them mid-conversation."""
    session = manager.create_session()
    manager.set_project(session.session_id, "proj_42")

    restored = _restart(db).get_session(session.session_id)

    assert restored.context.active_project_id == "proj_42"


def test_eviction_no_longer_destroys_a_conversation(manager, db):
    """The LRU used to be the only copy. It is now a cache — the evicted
    session has to come back from disk on the next access."""
    session = manager.create_session()
    manager.begin_stream(session.session_id, "ne me perds pas")
    manager.finish_stream(session.session_id, "promis")

    manager._sessions.clear()             # noqa: SLF001 — what eviction does

    recovered = manager.get_session(session.session_id)

    assert recovered is not None
    assert recovered.messages[0].content == "ne me perds pas"


def test_a_deleted_conversation_stays_deleted(manager, db):
    session = manager.create_session()
    manager.begin_stream(session.session_id, "à oublier")
    manager.finish_stream(session.session_id, "ok")

    assert manager.delete_session(session.session_id) is True
    assert _restart(db).get_session(session.session_id) is None


def test_an_unknown_session_is_still_unknown(manager):
    assert manager.get_session("conv_does_not_exist") is None


# ── degradation: a broken database must not break the chat ──────────────

class _BrokenStore:
    def sync(self, session):
        raise RuntimeError("disk on fire")

    def load(self, session_id):
        raise RuntimeError("disk on fire")

    def list_recent(self, limit=20, user_id=None):
        raise RuntimeError("disk on fire")

    def delete(self, session_id):
        raise RuntimeError("disk on fire")


def test_a_failing_store_degrades_to_the_old_behaviour():
    """Persistence is an improvement on losing everything, not a
    precondition for talking. A store that throws on every call must leave
    the manager exactly as usable as it was before HOS-101."""
    manager = ConversationManager(store=_BrokenStore())

    session = manager.create_session()
    manager.begin_stream(session.session_id, "toujours là ?")
    manager.finish_stream(session.session_id, "oui")

    assert len(manager.get_session(session.session_id).messages) == 2
    assert manager.list_sessions()[0]["session_id"] == session.session_id


# ── the store on its own ─────────────────────────────────────────────────

def test_sync_reports_only_what_it_wrote(db):
    """The return value is what lets a caller check the append is really an
    append rather than a rewrite."""
    store = SqliteConversationStore(db)
    manager = ConversationManager(store=store)
    session = manager.create_session()

    manager.begin_stream(session.session_id, "un")
    assert store.sync(session) == 0, "already-stored messages were rewritten"

    session.messages.append(session.messages[0])
    assert store.sync(session) == 1
