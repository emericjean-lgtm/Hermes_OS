"""Improvement Detector for Hermes OS (HOS-058).

Automatically detects:
- Underperforming runtime
- Unnecessary skills
- Missing skills
- Better model available
- Inefficient workflows
- Specialized agent needed
"""

from __future__ import annotations

import time
from typing import Any

from .evolution_models import (
    EvolutionProposal,
    EvolutionStatus,
    EvolutionType,
    OptimizationPattern,
    RiskLevel,
)


class ImprovementDetector:
    """Detects system improvements automatically.

    Maintains known optimization patterns and compares current metrics
    against them to suggest improvements.
    """

    def __init__(self) -> None:
        self._patterns: list[OptimizationPattern] = []
        self._detected: list[EvolutionProposal] = []
        self._known_bottlenecks: dict[str, int] = {}

    def add_pattern(self, pattern: OptimizationPattern) -> None:
        self._patterns.append(pattern)

    def detect_runtime_underperformance(
        self, current_latency: float, current_errors: float, threshold_latency: float = 500.0
    ) -> EvolutionProposal | None:
        """Detect underperforming runtime components."""
        evidence = []
        if current_latency > threshold_latency:
            evidence.append(f"latency {current_latency:.0f}ms > {threshold_latency:.0f}ms")
        if current_errors > 0.10:
            evidence.append(f"errors {current_errors*100:.1f}% > 10%")

        if len(evidence) >= 2:
            p = EvolutionProposal(
                proposal_id=f"detect_{int(time.time())}_runtime_perf",
                evolution_type=EvolutionType.RUNTIME_OPTIMIZATION,
                target_component="runtime.orchestrator",
                description="Runtime underperformance detected: " + "; ".join(evidence),
                expected_gain=25.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.75,
                tags=["detection", "runtime", "performance"],
            )
            self._detected.append(p)
            return p
        return None

    def detect_unnecessary_skills(self, unused_ratio: float, threshold: float = 0.4) -> EvolutionProposal | None:
        """Detect skills that are loaded but rarely used."""
        if unused_ratio > threshold:
            p = EvolutionProposal(
                proposal_id=f"detect_{int(time.time())}_unused_skills",
                evolution_type=EvolutionType.SKILL_IMPROVEMENT,
                target_component="skills.distribution",
                description=f"Unnecessary skills: {unused_ratio*100:.0f}% loaded but unused",
                expected_gain=10.0,
                risk_level=RiskLevel.LOW,
                confidence=0.85,
                tags=["detection", "skills", "cleanup"],
            )
            self._detected.append(p)
            return p
        return None

    def detect_missing_skills(self, failure_patterns: list[str]) -> EvolutionProposal | None:
        """Detect if repeated failures suggest a missing skill."""
        if len(failure_patterns) >= 3:
            p = EvolutionProposal(
                proposal_id=f"detect_{int(time.time())}_missing_skill",
                evolution_type=EvolutionType.SKILL_IMPROVEMENT,
                target_component="skills.distribution",
                description=f"Missing skill suggested by {len(failure_patterns)} failure patterns: {', '.join(failure_patterns[:3])}",
                expected_gain=30.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.6,
                tags=["detection", "skills", "missing"],
            )
            self._detected.append(p)
            return p
        return None

    def detect_model_switch_opportunity(
        self, current_score: float, available_better_score: float
    ) -> EvolutionProposal | None:
        """Detect if a better model is available."""
        if available_better_score > current_score * 1.2:
            improvement = (available_better_score - current_score) / current_score * 100
            p = EvolutionProposal(
                proposal_id=f"detect_{int(time.time())}_model_switch",
                evolution_type=EvolutionType.MODEL_SWITCH,
                target_component="runtime.orchestrator",
                description=f"Better model available: score {current_score:.2f} → {available_better_score:.2f} (+{improvement:.0f}%)",
                expected_gain=improvement,
                risk_level=RiskLevel.HIGH,
                confidence=0.65,
                tags=["detection", "model", "upgrade"],
            )
            self._detected.append(p)
            return p
        return None

    def detect_inefficient_workflow(
        self, repeat_rate: float, avg_duration: float
    ) -> EvolutionProposal | None:
        """Detect inefficient workflow patterns."""
        if repeat_rate > 0.3 and avg_duration > 5000:
            p = EvolutionProposal(
                proposal_id=f"detect_{int(time.time())}_workflow",
                evolution_type=EvolutionType.WORKFLOW_OPTIMIZATION,
                target_component="execution.engine",
                description=f"Inefficient workflow: {repeat_rate*100:.0f}% repeat rate, {avg_duration:.0f}ms avg",
                expected_gain=15.0,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.65,
                tags=["detection", "workflow"],
            )
            self._detected.append(p)
            return p
        return None

    def get_detected(self, limit: int = 50) -> list[EvolutionProposal]:
        return self._detected[-limit:]

    def get_patterns(self) -> list[OptimizationPattern]:
        return list(self._patterns)

    def record_bottleneck(self, component: str) -> None:
        self._known_bottlenecks[component] = self._known_bottlenecks.get(component, 0) + 1

    def get_frequent_bottlenecks(self, min_count: int = 3) -> list[tuple[str, int]]:
        return [(c, n) for c, n in sorted(self._known_bottlenecks.items(), key=lambda x: -x[1])
                if n >= min_count]

    def stats(self) -> dict[str, Any]:
        return {
            "patterns_known": len(self._patterns),
            "detected_count": len(self._detected),
            "detected_by_type": {
                t.value: sum(1 for d in self._detected if d.evolution_type == t)
                for t in EvolutionType
            },
            "known_bottlenecks": dict(self._known_bottlenecks),
        }
