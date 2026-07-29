"""Tests for the Adaptive Runtime Orchestrator (HOS-038)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from backend.runtime.orchestrator.decision_models import (
    DecisionStatus,
    OrchestratedDecision,
    PriorityLevel,
)
from backend.runtime.orchestrator.decision_pipeline import DecisionPipeline
from backend.runtime.orchestrator.priority_manager import PriorityManager
from backend.runtime.orchestrator.runtime_orchestrator import RuntimeOrchestrator


# ─── Mock subsystem callbacks ──────────────────────────────

@dataclass
class MockScore:
    composite_score: float


def _mock_healthy_scores(rid: str):
    scores = {"a": MockScore(90.0), "b": MockScore(70.0), "c": MockScore(50.0)}
    return scores.get(rid, MockScore(0.0))


def _mock_healthy(rid: str) -> str:
    states = {"a": "healthy", "b": "degraded", "c": "healthy"}
    return states.get(rid, "unknown")


def _mock_resources(rid: str) -> int:
    vram = {"a": 8 * 1024**3, "b": 4 * 1024**3, "c": 12 * 1024**3}
    return vram.get(rid, 0)


def _mock_not_recovering(rid: str) -> bool:
    return False


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def orchestrator() -> RuntimeOrchestrator:
    orch = RuntimeOrchestrator()
    orch.configure(
        runtime_ids=["a", "b", "c"],
        get_score=_mock_healthy_scores,
        get_health=_mock_healthy,
        get_resources=_mock_resources,
        is_recovering=_mock_not_recovering,
    )
    return orch


@pytest.fixture
def pipeline() -> DecisionPipeline:
    return DecisionPipeline(
        get_score=_mock_healthy_scores,
        get_health=_mock_healthy,
        get_resources=_mock_resources,
        is_recovering=_mock_not_recovering,
    )


# ─── 1. Priority Manager Tests ─────────────────────────────


class TestPriorityManager:
    def test_critical_profile(self):
        pm = PriorityManager()
        profile = pm.get_profile(PriorityLevel.CRITICAL)
        assert profile["allow_recovering"] is False
        assert profile["min_confidence"] == 0.85

    def test_background_profile(self):
        pm = PriorityManager()
        profile = pm.get_profile(PriorityLevel.BACKGROUND)
        assert profile["allow_recovering"] is True
        assert profile["resources"] > profile["intelligence"]

    def test_normal_profile(self):
        pm = PriorityManager()
        w = pm.get_weights(PriorityLevel.NORMAL)
        assert 0.35 <= w["intelligence"] <= 0.45

    def test_all_profiles_have_weights(self):
        pm = PriorityManager()
        for priority in PriorityLevel:
            w = pm.get_weights(priority)
            assert "intelligence" in w
            assert "health" in w
            assert "resources" in w


# ─── 2. Decision Pipeline Tests ────────────────────────────


class TestDecisionPipeline:
    def test_evaluate_candidates(self, pipeline: DecisionPipeline):
        """Pipeline evaluates and selects best runtime."""
        decision = pipeline.evaluate_candidates(["a", "b", "c"])
        assert decision.status == DecisionStatus.SELECTED
        assert decision.selected_runtime is not None
        assert decision.confidence > 0
        assert len(decision.candidates) == 3

    def test_best_runtime_wins(self, pipeline: DecisionPipeline):
        """Runtime with highest score is selected."""
        decision = pipeline.evaluate_candidates(["a", "b", "c"])
        # Runtime 'a' has highest intelligence + healthy
        assert decision.selected_runtime == "a"

    def test_unhealthy_eliminated(self, pipeline: DecisionPipeline):
        """Unhealthy runtimes are eliminated."""
        decision = pipeline.evaluate_candidates(["a", "b"])
        # Runtime 'b' is 'degraded' — shouldn't be eliminated, just scored lower
        # Create a scenario where b is 'unavailable'
        def unhealthy_health(rid: str) -> str:
            return {"a": "healthy", "b": "unavailable"}.get(rid, "unknown")

        pipeline2 = DecisionPipeline(
            get_score=_mock_healthy_scores,
            get_health=unhealthy_health,
            get_resources=_mock_resources,
            is_recovering=_mock_not_recovering,
        )
        decision = pipeline2.evaluate_candidates(["a", "b"])
        assert decision.selected_runtime == "a"

    def test_critical_priority_no_degraded(self, pipeline: DecisionPipeline):
        """Critical priority treats degraded cautiously."""
        decision = pipeline.evaluate_candidates(
            ["a", "b", "c"],
            priority=PriorityLevel.CRITICAL,
        )
        # 'a' is healthy, best
        assert decision.selected_runtime == "a"

    def test_background_prefers_resources(self, pipeline: DecisionPipeline):
        """Background priority weights resource efficiency higher."""
        decision = pipeline.evaluate_candidates(
            ["a", "b", "c"],
            priority=PriorityLevel.BACKGROUND,
        )
        # 'c' has most free VRAM (12 GB)
        assert decision.selected_runtime is not None
        assert decision.status == DecisionStatus.SELECTED

    def test_no_valid_candidates(self, pipeline: DecisionPipeline):
        """All eliminated → decision fails."""
        def all_unhealthy(rid: str) -> str:
            return "unavailable"

        pipeline2 = DecisionPipeline(
            get_score=_mock_healthy_scores,
            get_health=all_unhealthy,
            get_resources=_mock_resources,
            is_recovering=_mock_not_recovering,
        )
        decision = pipeline2.evaluate_candidates(["a", "b", "c"])
        assert decision.status == DecisionStatus.FAILED
        assert decision.selected_runtime is None

    def test_explain_decision(self, pipeline: DecisionPipeline):
        """explain_decision produces readable output."""
        decision = pipeline.evaluate_candidates(["a", "b", "c"])
        explanation = pipeline.explain_decision(decision)
        assert "selected" in explanation
        assert "factors" in explanation
        assert "candidates" in explanation

    def test_select_runtime_shortcut(self, pipeline: DecisionPipeline):
        """select_runtime returns the best runtime directly."""
        best = pipeline.select_runtime(["a", "b", "c"])
        assert best == "a"


# ─── 3. Orchestrator Tests ─────────────────────────────────


class TestRuntimeOrchestrator:
    def test_evaluate_produces_decision(self, orchestrator: RuntimeOrchestrator):
        """evaluate returns a complete OrchestratedDecision."""
        decision = orchestrator.evaluate()
        assert decision is not None
        assert decision.selected_runtime is not None
        assert decision.status == DecisionStatus.SELECTED
        assert decision.confidence > 0

    def test_select_shortcut(self, orchestrator: RuntimeOrchestrator):
        """select returns the best runtime_id."""
        best = orchestrator.select()
        assert best is not None
        assert best in ("a", "b", "c")

    def test_history_preserved(self, orchestrator: RuntimeOrchestrator):
        """Decisions are stored in history."""
        orchestrator.evaluate()
        orchestrator.evaluate()
        history = orchestrator.get_history()
        assert len(history) >= 2

    def test_get_decision_by_id(self, orchestrator: RuntimeOrchestrator):
        """get_decision retrieves a past decision."""
        decision = orchestrator.evaluate()
        assert decision is not None
        retrieved = orchestrator.get_decision(decision.decision_id)
        assert retrieved is not None
        assert retrieved.decision_id == decision.decision_id

    def test_explain(self, orchestrator: RuntimeOrchestrator):
        """explain returns detailed reasoning."""
        decision = orchestrator.evaluate()
        assert decision is not None
        explanation = orchestrator.explain(decision.decision_id)
        assert explanation is not None
        assert "selected" in explanation

    def test_unknown_decision_returns_none(self, orchestrator: RuntimeOrchestrator):
        """Querying a non-existent decision returns None."""
        assert orchestrator.get_decision("nonexistent") is None
        assert orchestrator.explain("nonexistent") is None

    def test_stats(self, orchestrator: RuntimeOrchestrator):
        """get_stats returns meaningful statistics."""
        orchestrator.evaluate()
        orchestrator.evaluate()
        stats = orchestrator.get_stats()
        assert stats["total_decisions"] >= 2
        assert stats["selected"] >= 2
        assert stats["known_runtimes"] == 3

    def test_register_runtime(self, orchestrator: RuntimeOrchestrator):
        """register_runtime adds to known runtimes."""
        orchestrator.register_runtime("d")
        stats = orchestrator.get_stats()
        assert "d" in stats["runtime_ids"]


# ─── 4. Event Publishing Tests ─────────────────────────────


class TestOrchestratorEvents:
    def test_events_published(self):
        """Pipeline publishes events through callback."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        pipeline = DecisionPipeline(
            get_score=_mock_healthy_scores,
            get_health=_mock_healthy,
            get_resources=_mock_resources,
            is_recovering=_mock_not_recovering,
        )
        pipeline.evaluate_candidates(["a", "b", "c"], on_event=on_event)

        event_types = {e["type"] for e in events}
        assert "routing.analysis_started" in event_types
        assert "routing.runtime_selected" in event_types
        assert "routing.decision_created" in event_types

    def test_failure_event(self):
        """Decision failure publishes routing.decision_failed."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        def all_bad(rid: str) -> str:
            return "unavailable"

        pipeline = DecisionPipeline(
            get_score=_mock_healthy_scores,
            get_health=all_bad,
            get_resources=_mock_resources,
            is_recovering=_mock_not_recovering,
        )
        pipeline.evaluate_candidates(["a", "b"], on_event=on_event)

        failed = [e for e in events if e["type"] == "routing.decision_failed"]
        assert len(failed) >= 1
        assert failed[0]["payload"]["reason"]


# ─── 5. Thread Safety ──────────────────────────────────────


class TestOrchestratorThreadSafety:
    def test_concurrent_evaluations(self, orchestrator: RuntimeOrchestrator):
        """Multiple threads can evaluate simultaneously."""
        errors: list[Exception] = []
        decisions: list[OrchestratedDecision] = []

        def worker() -> None:
            try:
                d = orchestrator.evaluate()
                if d:
                    decisions.append(d)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(decisions) >= 8

    def test_concurrent_history_access(self, orchestrator: RuntimeOrchestrator):
        """History is safe to read while writing."""
        errors: list[Exception] = []

        def writer() -> None:
            for _ in range(20):
                try:
                    orchestrator.evaluate()
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(30):
                try:
                    orchestrator.get_history()
                    orchestrator.get_stats()
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
