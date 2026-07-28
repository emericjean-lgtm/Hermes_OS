"""HOS-022 sentinel tests — Adaptive Skill Orchestrator.

Tests skill registration, selection, bundles, dependency resolution,
strategies, statistics and thread safety without network calls.
"""

from __future__ import annotations

import threading

import pytest

from backend.skills.orchestrator import (
    AdaptiveSkillOrchestrator,
    InMemorySkillRepository,
    SkillBundle,
    SkillDescriptor,
    SkillError,
    SkillEvent,
    SkillSelection,
    SkillSelectionStrategy,
    SkillStatistics,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_skill_descriptor_defaults() -> None:
    s = SkillDescriptor(id="s1", name="Test")
    assert s.id == "s1"
    assert s.name == "Test"
    assert s.priority == 5
    assert s.estimated_tokens == 0
    assert s.dependencies == frozenset()


def test_skill_bundle_defaults() -> None:
    b = SkillBundle(id="b1", name="Bundle")
    assert b.id == "b1"
    assert b.skill_ids == frozenset()


def test_skill_selection_defaults() -> None:
    sel = SkillSelection()
    assert sel.selected_skills == frozenset()
    assert sel.total_tokens == 0


def test_skill_statistics_defaults() -> None:
    st = SkillStatistics()
    assert st.total_skills_registered == 0
    assert st.load_success_rate == 1.0


def test_skill_selection_strategy_values() -> None:
    assert SkillSelectionStrategy.MINIMAL.value == "minimal"
    assert SkillSelectionStrategy.BALANCED.value == "balanced"
    assert SkillSelectionStrategy.EXHAUSTIVE.value == "exhaustive"
    assert SkillSelectionStrategy.PERFORMANCE.value == "performance"


# ============================================================================
# Repository
# ============================================================================


def test_repository_register_and_get() -> None:
    repo = InMemorySkillRepository()
    skill = SkillDescriptor(id="s1", name="Skill 1")
    repo.register(skill)
    assert repo.get("s1").name == "Skill 1"


def test_repository_unregister() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="S1"))
    repo.unregister("s1")
    assert repo.get("s1") is None


def test_repository_search_by_tags() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="S1", tags=frozenset({"code"})))
    repo.register(SkillDescriptor(id="s2", name="S2", tags=frozenset({"docs"})))
    results = repo.search(tags=frozenset({"code"}))
    assert len(results) == 1
    assert results[0].id == "s1"


def test_repository_search_by_text() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="Code Review", description="Review code"))
    repo.register(SkillDescriptor(id="s2", name="Write Docs"))
    results = repo.search(text="review")
    assert len(results) == 1
    assert results[0].id == "s1"


def test_repository_bundle_operations() -> None:
    repo = InMemorySkillRepository()
    bundle = SkillBundle(id="b1", name="B1", skill_ids=frozenset({"s1", "s2"}))
    repo.register_bundle(bundle)
    assert repo.get_bundle("b1").name == "B1"
    assert len(repo.list_bundles()) == 1


# ============================================================================
# Analyse mission
# ============================================================================


def test_analyse_mission_selects_matching_skills() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    orchestrator._repository.register(
        SkillDescriptor(id="chat", name="Chat", capabilities=frozenset({"chat"}), tags=frozenset({"core"}))
    )
    orchestrator._repository.register(
        SkillDescriptor(id="code", name="Coding", capabilities=frozenset({"code"}), tags=frozenset({"dev"}))
    )
    selection = orchestrator.analyse_mission(
        "Build a chat feature",
        required_capabilities=frozenset({"chat"}),
    )
    assert "chat" in selection.selected_skills
    assert selection.total_tokens >= 0


# ============================================================================
# select_skills
# ============================================================================


def test_select_skills_by_capability() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    orchestrator._repository.register(
        SkillDescriptor(id="s1", name="Chat", capabilities=frozenset({"chat"}))
    )
    orchestrator._repository.register(
        SkillDescriptor(id="s2", name="Code", capabilities=frozenset({"code"}))
    )
    selection = orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
    # s1 matches capability "chat"; select_skills also fills remaining by priority
    assert "s1" in selection.selected_skills


def test_select_skills_by_tags() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    orchestrator._repository.register(
        SkillDescriptor(id="s1", name="S1", tags=frozenset({"important"}))
    )
    orchestrator._repository.register(
        SkillDescriptor(id="s2", name="S2", tags=frozenset({"normal"}))
    )
    selection = orchestrator.select_skills(tags=frozenset({"important"}))
    assert "s1" in selection.selected_skills


# ============================================================================
# Selection strategies
# ============================================================================


def test_minimal_strategy_limits_selection() -> None:
    orchestrator = AdaptiveSkillOrchestrator(strategy=SkillSelectionStrategy.MINIMAL)
    orchestrator._repository.register(
        SkillDescriptor(id="s1", name="Chat", capabilities=frozenset({"chat"}), tags=frozenset({"core"}))
    )
    orchestrator._repository.register(
        SkillDescriptor(id="s2", name="Advanced Chat", capabilities=frozenset({"chat"}), tags=frozenset({"extra"}))
    )
    selection = orchestrator.analyse_mission("chat", required_capabilities=frozenset({"chat"}))
    # Minimal should select at least one matching skill.
    assert len(selection.selected_skills) >= 1


def test_exhaustive_strategy_includes_all() -> None:
    orchestrator = AdaptiveSkillOrchestrator(
        strategy=SkillSelectionStrategy.EXHAUSTIVE,
        max_skills=50,
        max_tokens=500000,
    )
    for i in range(5):
        orchestrator._repository.register(
            SkillDescriptor(id=f"s{i}", name=f"Skill{i}", capabilities=frozenset({"chat"}))
        )
    selection = orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
    # Exhaustive should include all matching skills.
    for i in range(5):
        assert f"s{i}" in selection.selected_skills


# ============================================================================
# Budget limits
# ============================================================================


def test_max_skills_limit() -> None:
    orchestrator = AdaptiveSkillOrchestrator(
        strategy=SkillSelectionStrategy.EXHAUSTIVE,
        max_skills=2,
        max_tokens=500000,
    )
    for i in range(5):
        orchestrator._repository.register(
            SkillDescriptor(id=f"s{i}", name=f"S{i}", capabilities=frozenset({"chat"}))
        )
    selection = orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
    assert len(selection.selected_skills) <= 2
    assert len(selection.rejected_skills) >= 3


# ============================================================================
# Bundles
# ============================================================================


def test_load_bundle() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="S1"))
    repo.register(SkillDescriptor(id="s2", name="S2"))
    repo.register_bundle(SkillBundle(id="b1", name="B1", skill_ids=frozenset({"s1", "s2"})))
    orchestrator = AdaptiveSkillOrchestrator(repository=repo)
    count = orchestrator.load_bundle("b1")
    assert count == 2


def test_load_bundle_nonexistent_raises() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    with pytest.raises(SkillError, match="not found"):
        orchestrator.load_bundle("nonexistent")


def test_unload_bundle() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="S1"))
    repo.register_bundle(SkillBundle(id="b1", name="B1", skill_ids=frozenset({"s1"})))
    orchestrator = AdaptiveSkillOrchestrator(repository=repo)
    orchestrator.load_bundle("b1")
    count = orchestrator.unload_bundle("b1")
    assert count == 1


# ============================================================================
# Recommendations
# ============================================================================


def test_recommend() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    orchestrator._repository.register(
        SkillDescriptor(id="code", name="Code Review", description="Review and improve code quality")
    )
    orchestrator._repository.register(
        SkillDescriptor(id="docs", name="Documentation", description="Write project documentation")
    )
    recs = orchestrator.recommend("I need to write documentation for my project")
    assert len(recs) >= 1
    assert recs[0].id == "docs"


# ============================================================================
# Events
# ============================================================================


def test_event_on_load() -> None:
    repo = InMemorySkillRepository()
    repo.register(SkillDescriptor(id="s1", name="S1"))
    repo.register_bundle(SkillBundle(id="b1", name="B1", skill_ids=frozenset({"s1"})))
    orchestrator = AdaptiveSkillOrchestrator(repository=repo)
    events: list[SkillEvent] = []
    orchestrator.on_event(lambda evt, _: events.append(evt))
    orchestrator.load_bundle("b1")
    assert SkillEvent.LOADED in events


# ============================================================================
# Statistics
# ============================================================================


def test_statistics() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    orchestrator._repository.register(SkillDescriptor(id="s1", name="S1"))
    orchestrator._repository.register(SkillDescriptor(id="s2", name="S2"))
    orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
    stats = orchestrator.get_statistics()
    assert stats.total_skills_registered == 2
    assert stats.total_selections == 1


# ============================================================================
# Explanation
# ============================================================================


def test_explain_selection() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    selection = orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
    explanation = orchestrator.explain_selection(selection)
    assert "Selected" in explanation
    assert "skill" in explanation.lower()


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_registration_and_selection() -> None:
    orchestrator = AdaptiveSkillOrchestrator()
    errors: list[Exception] = []

    def registerer() -> None:
        for i in range(50):
            orchestrator._repository.register(
                SkillDescriptor(id=f"s{i}", name=f"S{i}", capabilities=frozenset({"chat"}))
            )

    def selector() -> None:
        for _ in range(50):
            try:
                orchestrator.select_skills(required_capabilities=frozenset({"chat"}))
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=registerer)
    t2 = threading.Thread(target=selector)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    stats = orchestrator.get_statistics()
    assert stats.total_skills_registered == 50
    assert stats.total_selections == 50
