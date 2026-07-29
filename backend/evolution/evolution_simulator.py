"""Evolution Simulator for Hermes OS (HOS-058).

Simulates the impact of evolution proposals before they are applied.
Uses Runtime Simulation Engine (HOS-039) integration for realistic estimates.
"""

from __future__ import annotations

import random
import time
from typing import Any

from .evolution_models import (
    EvolutionExperiment,
    EvolutionProposal,
    EvolutionStatus,
    EvolutionType,
)


class EvolutionSimulator:
    """Simulates evolution proposals to predict impact.

    Provides confidence-scored simulations of:
    - Performance impact
    - Resource cost
    - Risk assessment
    """

    def __init__(self) -> None:
        self._experiments: list[EvolutionExperiment] = []

    def simulate(self, proposal: EvolutionProposal, current_metrics: dict[str, float] | None = None) -> EvolutionExperiment:
        """Simulate the impact of a proposal.

        Uses heuristics based on evolution type and historical patterns.
        In production, delegates to the Runtime Simulation Engine (HOS-039).
        """
        before = current_metrics or {"latency_ms": 500, "success_rate": 0.75, "cost": 1.0}
        after = self._estimate_impact(proposal, before)
        result = self._evaluate_result(before, after)

        experiment = EvolutionExperiment(
            experiment_id=f"exp_{int(time.time())}_{random.randint(100,999)}",
            proposal_id=proposal.proposal_id,
            before_metrics=before,
            after_metrics=after,
            result=result,
            conclusion=self._generate_conclusion(proposal, result, after),
        )
        self._experiments.append(experiment)
        return experiment

    def _estimate_impact(self, proposal: EvolutionProposal, before: dict[str, float]) -> dict[str, float]:
        """Estimate the after-metrics based on proposal type."""
        confidence = proposal.confidence
        noise = 1.0 + random.uniform(-0.1, 0.1)  # ±10% noise

        after = dict(before)

        if proposal.evolution_type in (EvolutionType.RUNTIME_OPTIMIZATION, EvolutionType.MODEL_SWITCH):
            latency_reduction = proposal.expected_gain / 100.0 * confidence * noise
            after["latency_ms"] = max(10, before.get("latency_ms", 500) * (1.0 - latency_reduction))
            after["success_rate"] = min(1.0, before.get("success_rate", 0.75) * (1.0 + latency_reduction * 0.3))

        elif proposal.evolution_type in (EvolutionType.SKILL_IMPROVEMENT, EvolutionType.AGENT_IMPROVEMENT):
            improvement = proposal.expected_gain / 100.0 * confidence * noise
            after["success_rate"] = min(1.0, before.get("success_rate", 0.75) * (1.0 + improvement))
            after["cost"] = before.get("cost", 1.0) * (1.0 - improvement * 0.5)

        elif proposal.evolution_type == EvolutionType.WORKFLOW_OPTIMIZATION:
            improvement = proposal.expected_gain / 100.0 * confidence * noise
            after["latency_ms"] = max(10, before.get("latency_ms", 500) * (1.0 - improvement * 0.5))

        elif proposal.evolution_type == EvolutionType.MEMORY_OPTIMIZATION:
            hit_rate_improvement = proposal.expected_gain / 100.0 * confidence * noise
            after["hit_rate"] = min(1.0, before.get("hit_rate", 0.5) * (1.0 + hit_rate_improvement))

        return after

    def _evaluate_result(self, before: dict[str, float], after: dict[str, float]) -> str:
        """Determine if the simulation shows improvement."""
        improvements = 0
        regressions = 0

        for key in before:
            if key == "latency_ms":
                if after.get(key, 0) < before[key]:
                    improvements += 1
                elif after.get(key, 0) > before[key]:
                    regressions += 1
            elif key == "cost":
                if after.get(key, 0) < before[key]:
                    improvements += 1
                elif after.get(key, 0) > before[key]:
                    regressions += 1
            else:  # higher is better
                if after.get(key, 0) > before[key]:
                    improvements += 1
                elif after.get(key, 0) < before[key]:
                    regressions += 1

        if improvements > regressions:
            return "improvement"
        elif regressions > improvements:
            return "regression"
        return "no_change"

    def _generate_conclusion(self, proposal: EvolutionProposal, result: str, after: dict) -> str:
        if result == "improvement":
            return f"Proposal {proposal.proposal_id}: Expected improvement of ~{proposal.expected_gain:.0f}% with confidence {proposal.confidence:.0%}"
        elif result == "regression":
            return f"Proposal {proposal.proposal_id}: Risk of regression detected, recommend rejection"
        return f"Proposal {proposal.proposal_id}: No significant change expected"

    def get_experiments(self, proposal_id: str | None = None) -> list[EvolutionExperiment]:
        if proposal_id:
            return [e for e in self._experiments if e.proposal_id == proposal_id]
        return list(self._experiments)

    def stats(self) -> dict[str, Any]:
        experiments = self._experiments
        return {
            "total_experiments": len(experiments),
            "improvements": sum(1 for e in experiments if e.result == "improvement"),
            "regressions": sum(1 for e in experiments if e.result == "regression"),
            "no_changes": sum(1 for e in experiments if e.result == "no_change"),
        }
