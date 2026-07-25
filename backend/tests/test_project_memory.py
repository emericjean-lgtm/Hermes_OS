"""§12 — project memory: the level between the conversation and the
permanent store.

The storage already existed; what this covers is the part that didn't —
telling the three levels apart, and loading a project's memory as a
structured whole rather than a flat list the caller has to sort.
"""
from __future__ import annotations

import pytest

from backend.memory import episodic, project_memory
from backend.memory.db import Base, make_engine, make_session_factory
from backend.memory.project_memory import MemoryLevel, level_for


@pytest.fixture
def session(tmp_path):
    engine = make_engine(str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        yield s


# ── the vocabulary ───────────────────────────────────────────────────
@pytest.mark.parametrize("type_", ["architecture", "roadmap", "decision", "documentation"])
def test_project_types(type_):
    assert level_for(type_) is MemoryLevel.PROJECT


@pytest.mark.parametrize("type_", ["preference", "habit", "rule", "history"])
def test_permanent_types(type_):
    assert level_for(type_) is MemoryLevel.PERMANENT


def test_unknown_type_is_unclassified_not_an_error():
    """A vocabulary that rejected unknown types on introduction would be
    a migration: entries written before it exists must keep working."""
    assert level_for("reflection") is MemoryLevel.UNCLASSIFIED
    assert level_for("n_importe_quoi") is MemoryLevel.UNCLASSIFIED


def test_level_lookup_is_case_and_space_insensitive():
    assert level_for("  Decision ") is MemoryLevel.PROJECT


def test_known_types_lists_both_levels():
    vocab = project_memory.known_types()

    assert set(vocab) == {"project", "permanent"}
    assert "architecture" in vocab["project"]
    assert "preference" in vocab["permanent"]


# ── the grouped read ─────────────────────────────────────────────────
def test_brief_groups_by_type(session):
    for type_, content in [
        ("architecture", "FastAPI + SQLite + ChromaDB"),
        ("roadmap", "Git phase 2 puis execution de code"),
        ("decision", "HSE retire du vocabulaire"),
        ("decision", "Aegis garde la securite"),
        ("documentation", "Voir AUDIT_CONFORMITE.md"),
    ]:
        episodic.add_memory(session, type_=type_, content=content, project_id="p1")

    brief = project_memory.project_brief(session, "p1")

    assert brief.total == 5
    assert len(brief.by_type["decision"]) == 2
    assert brief.by_type["architecture"][0]["content"].startswith("FastAPI")
    assert brief.other == []


def test_all_four_sections_are_always_present(session):
    """A caller renders a stable structure without checking for missing
    keys — even for a project that has only one kind of memory."""
    episodic.add_memory(session, type_="decision", content="seule entree", project_id="p1")

    brief = project_memory.project_brief(session, "p1")

    assert set(brief.by_type) == {"architecture", "roadmap", "decision", "documentation"}
    assert brief.by_type["roadmap"] == []


def test_off_vocabulary_entries_are_surfaced_not_dropped(session):
    """A typo'd type would otherwise make an entry invisible — the worst
    failure mode for a memory store."""
    episodic.add_memory(session, type_="architecure", content="faute de frappe", project_id="p1")

    brief = project_memory.project_brief(session, "p1")

    assert brief.total == 1
    assert len(brief.other) == 1
    assert brief.other[0]["content"] == "faute de frappe"
    assert brief.other[0]["level"] == "unclassified"


def test_brief_is_scoped_to_one_project(session):
    episodic.add_memory(session, type_="decision", content="pour p1", project_id="p1")
    episodic.add_memory(session, type_="decision", content="pour p2", project_id="p2")

    brief = project_memory.project_brief(session, "p1")

    assert brief.total == 1
    assert brief.by_type["decision"][0]["content"] == "pour p1"


def test_permanent_memory_is_not_folded_into_a_project_brief(session):
    """Mixing the levels is how a project-specific decision ends up being
    applied globally later."""
    episodic.add_memory(session, type_="preference", content="prefere le francais")
    episodic.add_memory(session, type_="decision", content="decision projet", project_id="p1")

    brief = project_memory.project_brief(session, "p1")

    assert brief.total == 1
    assert all("prefere" not in e["content"] for section in brief.by_type.values() for e in section)


def test_empty_project_returns_an_empty_but_valid_brief(session):
    brief = project_memory.project_brief(session, "inconnu")

    assert brief.total == 0
    assert brief.other == []
    assert set(brief.by_type) == {"architecture", "roadmap", "decision", "documentation"}


def test_entries_carry_their_level(session):
    episodic.add_memory(session, type_="roadmap", content="etape suivante", project_id="p1")

    entry = project_memory.project_brief(session, "p1").by_type["roadmap"][0]

    assert entry["level"] == "project"
    assert "created_at" in entry and "id" in entry


# ── the permanent level, kept separate ───────────────────────────────
def test_permanent_memory_excludes_project_entries(session):
    """The bug the dashboard revealed: list_memories(project_id=None)
    means "don't filter", not "no project", so the permanent view was
    listing a project's architecture notes as if they were global rules."""
    episodic.add_memory(session, type_="preference", content="repond en francais")
    episodic.add_memory(session, type_="rule", content="jamais de push sur main")
    episodic.add_memory(session, type_="architecture", content="specifique au projet", project_id="p1")

    permanent = project_memory.permanent_memory(session)

    contents = {e["content"] for e in permanent}
    assert contents == {"repond en francais", "jamais de push sur main"}
    assert all(e["level"] == "permanent" for e in permanent)


def test_permanent_memory_is_empty_when_everything_is_scoped(session):
    episodic.add_memory(session, type_="decision", content="projet only", project_id="p1")

    assert project_memory.permanent_memory(session) == []


def test_the_two_levels_never_overlap(session):
    episodic.add_memory(session, type_="preference", content="globale")
    episodic.add_memory(session, type_="decision", content="projet", project_id="p1")

    permanent = {e["content"] for e in project_memory.permanent_memory(session)}
    brief = project_memory.project_brief(session, "p1")
    project = {e["content"] for section in brief.by_type.values() for e in section}

    assert permanent & project == set()
