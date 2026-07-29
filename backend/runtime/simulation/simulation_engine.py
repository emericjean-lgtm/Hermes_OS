"""Simulation Engine for the Runtime Simulation Engine (HOS-039).

Simulates task execution decisions before they run in production.
Integrates with RuntimeOrchestrator for simulate_before_execute.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.runtime.simulation.resource_predictor import ResourcePredictor
from backend.runtime.simulation.risk_analyzer import RiskAnalyzer
from backend.runtime.simulation.simulation_models import (
    RiskAssessment,
    RiskLevel,
    SimulatedCandidate,
    SimulationResult,
    SimulationStatus,
)


class SimulationEngine:
    """Simulates runtime decisions and predicts outcomes.

    Thread-safe. Integrates with:
    - ResourcePredictor for resource estimates
    - RiskAnalyzer for risk assessment
    - RuntimeOrchestrator via simulate_before_execute
    """

    def __init__(
        self,
        predictor: Optional[ResourcePredictor] = None,
        risk_analyzer: Optional[RiskAnalyzer] = None,
        get_candidates: Optional[Callable[[], list[str]]] = None,
        get_score: Optional[Callable[[str], Optional[Any]]] = None,
        get_health: Optional[Callable[[str], str]] = None,
        get_model: Optional[Callable[[str], str]] = None,
        get_stats: Optional[Callable[[str], dict]] = None,
        is_recovering: Optional[Callable[[str], bool]] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._predictor = predictor or ResourcePredictor()
        self._risk_analyzer = risk_analyzer or RiskAnalyzer()
        self._get_candidates = get_candidates or (lambda: [])
        self._get_score = get_score or (lambda rid: None)
        self._get_health = get_health or (lambda rid: "unknown")
        self._get_model = get_model or (lambda rid: "")
        self._get_stats = get_stats or (lambda rid: {})
        self._is_recovering = is_recovering or (lambda rid: False)
        self._on_event = on_event
        self._history: list[SimulationResult] = []

    # ── Configuration ──────────────────────────────────────

    def configure(
        self,
        get_candidates: Optional[Callable[[], list[str]]] = None,
        get_score: Optional[Callable] = None,
        get_health: Optional[Callable] = None,
        get_model: Optional[Callable] = None,
        get_stats: Optional[Callable] = None,
        is_recovering: Optional[Callable] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        with self._lock:
            if get_candidates: self._get_candidates = get_candidates
            if get_score: self._get_score = get_score
            if get_health: self._get_health = get_health
            if get_model: self._get_model = get_model
            if get_stats: self._get_stats = get_stats
            if is_recovering: self._is_recovering = is_recovering
            if on_event: self._on_event = on_event

    # ── Simulation ─────────────────────────────────────────

    def simulate_task(
        self,
        task_context: Optional[dict] = None,
        task_type: str = "default",
    ) -> SimulationResult:
        """Simulate a task execution on all available candidates."""
        result = SimulationResult(
            task_context=task_context or {},
            status=SimulationStatus.RUNNING,
        )

        if self._on_event:
            self._on_event(
                "simulation.started",
                {"task_type": task_type},
                severity="info",
            )

        # Get candidates
        candidates = self._get_candidates()
        if not candidates:
            result.status = SimulationStatus.FAILED
            result.summary = "No candidates available"
            return result

        # Simulate each candidate
        simulated: list[SimulatedCandidate] = []
        for runtime_id in candidates:
            sc = SimulatedCandidate(runtime_id=runtime_id)

            # Intelligence score
            score_obj = self._get_score(runtime_id)
            sc.predicted_score = (
                score_obj.composite_score
                if score_obj and hasattr(score_obj, "composite_score")
                else 0.0
            )

            # Resource prediction
            sc.resource_prediction = self._predictor.predict(
                runtime_id, task_type=task_type,
            )

            # Risk analysis
            sc.risk_assessment = self._risk_analyzer.analyze(
                runtime_id,
                sc.resource_prediction,
            )

            # Warnings
            if sc.risk_assessment.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                sc.warnings.extend(sc.risk_assessment.issues)

            simulated.append(sc)

        # Sort by score (best first)
        simulated.sort(key=lambda s: s.predicted_score, reverse=True)

        # Recommend best low-risk candidate
        best = None
        for s in simulated:
            if s.risk_assessment.level in (RiskLevel.LOW, RiskLevel.MEDIUM):
                best = s
                best.is_recommended = True
                break

        # Fallback: accept any candidate
        if best is None and simulated:
            best = simulated[0]
            best.is_recommended = True
            best.warnings.append(f"High risk accepted: {best.risk_assessment.level}")

        result.candidates = simulated
        result.recommended_runtime = best.runtime_id if best else None
        result.overall_risk = best.risk_assessment.level if best else RiskLevel.CRITICAL
        result.status = SimulationStatus.COMPLETED
        result.summary = (
            f"Recommended {best.runtime_id} (score={best.predicted_score:.1f}, "
            f"risk={best.risk_assessment.level})"
            if best
            else "No suitable candidate found"
        )
        result.completed_at = datetime.now(timezone.utc)

        # Publish
        if self._on_event:
            ev_type = "simulation.warning" if result.overall_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) else "simulation.completed"
            self._on_event(
                ev_type,
                {
                    "simulation_id": result.simulation_id,
                    "recommended": result.recommended_runtime,
                    "risk": result.overall_risk.value,
                },
                severity="warning" if ev_type == "simulation.warning" else "info",
            )

        with self._lock:
            self._history.append(result)
            if len(self._history) > 500:
                self._history = self._history[-500:]

        return result

    def simulate_before_execute(
        self,
        task_context: Optional[dict] = None,
        task_type: str = "default",
    ) -> Optional[str]:
        """Run simulation and return recommended runtime (or None)."""
        result = self.simulate_task(task_context, task_type)
        return result.recommended_runtime

    # ── Query ───────────────────────────────────────────────

    def get_simulation(self, simulation_id: str) -> Optional[SimulationResult]:
        with self._lock:
            for s in self._history:
                if s.simulation_id == simulation_id:
                    return s
        return None

    def get_history(self, limit: int = 20) -> list[SimulationResult]:
        with self._lock:
            return self._history[-limit:]

    @property
    def total_simulations(self) -> int:
        with self._lock:
            return len(self._history)
