"""Risk Analyzer for the Runtime Simulation Engine (HOS-039).

Analyzes failure risk, overload risk, and instability of simulated decisions.
"""

from __future__ import annotations

from typing import Callable, Optional

from backend.runtime.simulation.simulation_models import (
    ResourcePrediction,
    RiskAssessment,
    RiskLevel,
)


class RiskAnalyzer:
    """Assesses risk for a simulated runtime decision."""

    def __init__(
        self,
        get_stats: Optional[Callable[[str], dict]] = None,
        get_health: Optional[Callable[[str], str]] = None,
        is_recovering: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._get_stats = get_stats or (lambda rid: {})
        self._get_health = get_health or (lambda rid: "unknown")
        self._is_recovering = is_recovering or (lambda rid: False)

    def analyze(
        self,
        runtime_id: str,
        prediction: ResourcePrediction,
        load_pct: float = 0.0,
    ) -> RiskAssessment:
        """Assess risk for a candidate."""
        stats = self._get_stats(runtime_id) or {}
        health = self._get_health(runtime_id)
        recovering = self._is_recovering(runtime_id)

        issues: list[str] = []
        scores: list[float] = []

        # 1. Failure probability (from history)
        total = stats.get("total", 0)
        failures = stats.get("failures", 0)
        if total > 0:
            failure_prob = failures / total
            if failure_prob > 0.3:
                issues.append(f"High failure rate: {failure_prob:.0%}")
                scores.append(failure_prob * 50)
            elif failure_prob > 0.1:
                scores.append(failure_prob * 25)
        else:
            failure_prob = 0.0

        # 2. Overload probability (from predicted load)
        overload_prob = 0.0
        if prediction.expected_load_pct > 85:
            issues.append(f"High expected load: {prediction.expected_load_pct:.0f}%")
            overload_prob = min(0.8, (prediction.expected_load_pct - 80) / 20 * 0.4)
            scores.append(overload_prob * 40)
        elif prediction.expected_load_pct > 70:
            overload_prob = 0.1
            scores.append(overload_prob * 20)

        # 3. Instability (from health)
        instability_score = 0.0
        if health == "degraded":
            instability_score = 30.0
            issues.append("Runtime health degraded")
            scores.append(15.0)
        elif health == "critical" or health == "unavailable":
            instability_score = 80.0
            issues.append(f"Runtime health: {health}")
            scores.append(40.0)

        # 4. Recovery penalty
        if recovering:
            instability_score += 20.0
            issues.append("Runtime in recovery")
            scores.append(10.0)

        # Risk score (0-100)
        risk_score = min(100.0, sum(scores) + overload_prob * 30 + instability_score * 0.5)

        # Risk level
        if risk_score >= 60:
            level = RiskLevel.CRITICAL
        elif risk_score >= 35:
            level = RiskLevel.HIGH
        elif risk_score >= 12:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return RiskAssessment(
            level=level,
            score=round(risk_score, 2),
            failure_probability=round(failure_prob, 3),
            overload_probability=round(overload_prob, 3),
            instability_score=round(instability_score, 2),
            issues=issues,
        )
