"""Tests for the Runtime Simulation Engine (HOS-039)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest

from backend.runtime.simulation.resource_predictor import ResourcePredictor
from backend.runtime.simulation.risk_analyzer import RiskAnalyzer
from backend.runtime.simulation.simulation_engine import SimulationEngine
from backend.runtime.simulation.simulation_models import (
    ResourcePrediction,
    RiskLevel,
    SimulationStatus,
)


# ─── Mock helpers ──────────────────────────────────────────

@dataclass
class MockScore:
    composite_score: float


def _mock_candidates() -> list[str]:
    return ["a", "b", "c"]


def _mock_score(rid: str):
    scores = {"a": MockScore(90.0), "b": MockScore(70.0), "c": MockScore(50.0)}
    return scores.get(rid, MockScore(0.0))


def _mock_health(rid: str) -> str:
    return {"a": "healthy", "b": "healthy", "c": "degraded"}.get(rid, "healthy")


def _mock_model(rid: str) -> str:
    return {"a": "qwen3:14b", "b": "deepseek-r1:14b", "c": "qwen3-coder:30b"}.get(rid, "")


def _mock_stats(rid: str) -> dict:
    return {
        "a": {"total": 50, "failures": 2, "avg_duration_ms": 150.0},
        "b": {"total": 30, "failures": 6, "avg_duration_ms": 350.0},
        "c": {"total": 20, "failures": 1, "avg_duration_ms": 250.0},
    }.get(rid, {})


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def engine() -> SimulationEngine:
    eng = SimulationEngine(
        ResourcePredictor(get_model=_mock_model, get_stats=_mock_stats),
        RiskAnalyzer(get_stats=_mock_stats, get_health=_mock_health),
    )
    eng.configure(
        get_candidates=_mock_candidates,
        get_score=_mock_score,
        get_health=_mock_health,
        get_model=_mock_model,
        get_stats=_mock_stats,
    )
    return eng


# ─── 1. Resource Predictor Tests ───────────────────────────


class TestResourcePredictor:
    def test_predict_chat(self):
        predictor = ResourcePredictor(get_model=_mock_model, get_stats=_mock_stats)
        pred = predictor.predict("a", task_type="chat", estimated_tokens=500)
        assert pred.vram_mb > 0
        assert pred.ram_mb > pred.vram_mb
        assert pred.estimated_duration_ms > 0

    def test_predict_code_uses_more_vram(self):
        predictor = ResourcePredictor(get_model=_mock_model, get_stats=_mock_stats)
        chat = predictor.predict("a", task_type="chat")
        code = predictor.predict("a", task_type="code")
        assert code.vram_mb > chat.vram_mb

    def test_predict_unknown_model_defaults(self):
        predictor = ResourcePredictor(get_model=lambda r: "unknown-model")
        pred = predictor.predict("x")
        assert pred.vram_mb == 8192  # Default

    def test_concurrent_capacity(self):
        predictor = ResourcePredictor(get_model=_mock_model)
        pred = predictor.predict("a", task_type="chat")
        assert pred.concurrent_capacity >= 1


# ─── 2. Risk Analyzer Tests ────────────────────────────────


class TestRiskAnalyzer:
    def test_low_risk_healthy(self):
        analyzer = RiskAnalyzer(get_stats=_mock_stats, get_health=_mock_health)
        pred = ResourcePrediction(vram_mb=8192, expected_load_pct=50.0)
        risk = analyzer.analyze("a", pred)
        assert risk.level == RiskLevel.LOW
        assert risk.score < 15

    def test_high_risk_degraded(self):
        analyzer = RiskAnalyzer(get_stats=_mock_stats, get_health=_mock_health)
        pred = ResourcePrediction(vram_mb=8192, expected_load_pct=50.0)
        risk = analyzer.analyze("c", pred)  # degraded
        assert risk.level in (RiskLevel.MEDIUM, RiskLevel.HIGH)

    def test_recovering_adds_risk(self):
        analyzer = RiskAnalyzer(get_stats=_mock_stats, get_health=_mock_health, is_recovering=lambda r: True)
        pred = ResourcePrediction(vram_mb=8192, expected_load_pct=50.0)
        risk = analyzer.analyze("a", pred)
        assert risk.instability_score > 0

    def test_high_load_increases_risk(self):
        analyzer = RiskAnalyzer(get_stats=_mock_stats, get_health=_mock_health)
        pred = ResourcePrediction(vram_mb=8192, expected_load_pct=90.0)
        risk = analyzer.analyze("a", pred)
        assert risk.overload_probability > 0
        assert risk.level != RiskLevel.LOW


# ─── 3. Simulation Engine Tests ────────────────────────────


class TestSimulationEngine:
    def test_simulate_task(self, engine: SimulationEngine):
        result = engine.simulate_task(task_type="chat")
        assert result.status == SimulationStatus.COMPLETED
        assert result.recommended_runtime is not None
        assert len(result.candidates) == 3
        assert result.summary

    def test_best_candidate_recommended(self, engine: SimulationEngine):
        result = engine.simulate_task(task_type="chat")
        assert result.recommended_runtime == "a"  # Highest score, healthy

    def test_simulate_before_execute(self, engine: SimulationEngine):
        best = engine.simulate_before_execute(task_type="chat")
        assert best is not None
        assert best in ("a", "b", "c")

    def test_history(self, engine: SimulationEngine):
        engine.simulate_task()
        engine.simulate_task()
        history = engine.get_history()
        assert len(history) >= 2

    def test_get_simulation(self, engine: SimulationEngine):
        result = engine.simulate_task()
        retrieved = engine.get_simulation(result.simulation_id)
        assert retrieved is not None
        assert retrieved.simulation_id == result.simulation_id

    def test_no_candidates(self):
        eng = SimulationEngine()
        eng.configure(get_candidates=lambda: [])
        result = eng.simulate_task()
        assert result.status == SimulationStatus.FAILED

    def test_each_candidate_has_predictions(self, engine: SimulationEngine):
        result = engine.simulate_task(task_type="code")
        for c in result.candidates:
            assert c.resource_prediction.vram_mb > 0
            assert c.risk_assessment is not None


# ─── 4. Event Publishing Tests ─────────────────────────────


class TestSimulationEvents:
    def test_simulation_started_event(self):
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        eng = SimulationEngine(on_event=on_event)
        eng.configure(get_candidates=_mock_candidates, get_score=_mock_score, get_health=_mock_health)
        eng.simulate_task()

        started = [e for e in events if e["type"] == "simulation.started"]
        assert len(started) == 1

    def test_simulation_completed_event(self):
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        eng = SimulationEngine(on_event=on_event)
        eng.configure(get_candidates=_mock_candidates, get_score=_mock_score, get_health=_mock_health)
        eng.simulate_task()

        completed = [e for e in events if e["type"] == "simulation.completed"]
        assert len(completed) == 1
        assert completed[0]["payload"]["simulation_id"]


# ─── 5. Thread Safety ──────────────────────────────────────


class TestSimulationThreadSafety:
    def test_concurrent_simulations(self, engine: SimulationEngine):
        errors: list[Exception] = []

        def worker() -> None:
            try:
                engine.simulate_task(task_type="chat")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert engine.total_simulations == 10

    def test_concurrent_history_access(self, engine: SimulationEngine):
        engine.simulate_task()
        errors: list[Exception] = []

        def reader() -> None:
            for _ in range(50):
                try:
                    engine.get_history()
                except Exception as e:
                    errors.append(e)

        def writer() -> None:
            for _ in range(20):
                try:
                    engine.simulate_task()
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
