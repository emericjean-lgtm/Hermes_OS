"""Runtime Scorer for the Runtime Intelligence Layer (HOS-037).

Computes composite scores and generates recommendations.
"""

from __future__ import annotations

from typing import Optional

from backend.runtime.intelligence.decision_memory import DecisionMemory
from backend.runtime.intelligence.intelligence_models import (
    Recommendation,
    RuntimeScore,
    TaskContext,
)
from backend.runtime.intelligence.performance_analyzer import PerformanceAnalyzer


class RuntimeScorer:
    """Computes runtime scores and generates recommendations."""

    def __init__(self, memory: DecisionMemory, analyzer: PerformanceAnalyzer) -> None:
        self._memory = memory
        self._analyzer = analyzer
        # Weights for composite score
        self._weights = {
            "performance": 0.35,
            "reliability": 0.40,
            "efficiency": 0.25,
        }

    # ── Scoring ────────────────────────────────────────────

    def get_runtime_score(self, runtime_id: str) -> RuntimeScore:
        """Compute full score for a runtime."""
        stats = self._memory.get_stats(runtime_id)

        # Performance: success rate (already 0-100 scale conceptually)
        perf = self._analyzer.success_rate_weighted(runtime_id) * 100

        # Reliability: combination of success rate and stability
        stability = self._analyzer.stability_score(runtime_id)
        reliability = 0.6 * perf + 0.4 * stability

        # Resource efficiency
        efficiency = self._analyzer.resource_efficiency(runtime_id)

        # Composite
        composite = round(
            self._weights["performance"] * perf
            + self._weights["reliability"] * reliability
            + self._weights["efficiency"] * efficiency,
            2,
        )

        return RuntimeScore(
            runtime_id=runtime_id,
            performance_score=round(perf, 2),
            reliability_score=round(reliability, 2),
            resource_efficiency=round(efficiency, 2),
            composite_score=composite,
            total_executions=stats["total"],
            successes=stats["successes"],
            failures=stats["failures"],
            fallbacks=stats["fallbacks"],
            avg_duration_ms=stats["avg_duration_ms"],
        )

    def get_all_scores(self) -> list[RuntimeScore]:
        """Score all known runtimes, sorted by composite."""
        ids = self._memory.get_all_runtime_ids()
        scores = [self.get_runtime_score(rid) for rid in ids]
        return sorted(scores, key=lambda s: s.composite_score, reverse=True)

    def compare_runtimes(self, runtime_a: str, runtime_b: str) -> dict:
        """Compare two runtimes side by side."""
        score_a = self.get_runtime_score(runtime_a)
        score_b = self.get_runtime_score(runtime_b)
        return {
            runtime_a: {
                "composite": score_a.composite_score,
                "performance": score_a.performance_score,
                "reliability": score_a.reliability_score,
                "efficiency": score_a.resource_efficiency,
                "total_executions": score_a.total_executions,
            },
            runtime_b: {
                "composite": score_b.composite_score,
                "performance": score_b.performance_score,
                "reliability": score_b.reliability_score,
                "efficiency": score_b.resource_efficiency,
                "total_executions": score_b.total_executions,
            },
        }

    # ── Recommendations ────────────────────────────────────

    def recommend_runtime(
        self,
        context: Optional[TaskContext] = None,
        top_n: int = 3,
    ) -> Optional[Recommendation]:
        """Recommend the best runtime for a task context."""
        all_scores = self.get_all_scores()
        if not all_scores:
            return None

        # Start with base scores
        scored: list[tuple[RuntimeScore, float]] = [
            (s, s.composite_score) for s in all_scores
        ]

        # Apply context adjustments
        if context:
            scored = self._apply_context(scored, context)

        scored.sort(key=lambda x: x[1], reverse=True)

        best = scored[0]
        reasoning: list[str] = [
            f"Runtime {best[0].runtime_id} selected with score {best[1]:.1f}",
            f"Success rate: {best[0].success_rate*100:.1f}% ({best[0].successes}/{best[0].total_executions})",
            f"Avg latency: {best[0].avg_duration_ms:.1f}ms",
            f"Reliability: {best[0].reliability_score:.1f}",
        ]

        alternatives = [
            (s.runtime_id, w) for s, w in scored[1 : 1 + top_n]
        ]

        confidence = min(95.0, 50.0 + best[0].composite_score / 2)

        return Recommendation(
            runtime_id=best[0].runtime_id,
            score=best[1],
            confidence=confidence,
            reasoning=reasoning,
            alternatives=alternatives,
        )

    def _apply_context(
        self,
        scored: list[tuple[RuntimeScore, float]],
        context: TaskContext,
    ) -> list[tuple[RuntimeScore, float]]:
        """Adjust scores based on task context."""
        adjusted: list[tuple[RuntimeScore, float]] = []

        for score, base in scored:
            w = base

            # Prefer runtimes with low latency if max_latency_ms is set
            if context.max_latency_ms is not None:
                if score.avg_duration_ms <= context.max_latency_ms:
                    w += 5
                else:
                    w -= 10

            # Prefer local runtimes if prefer_local
            if context.prefer_local:
                # Not directly detectable, but we can adjust based on resource efficiency
                if score.resource_efficiency > 50:
                    w += 3

            # Priority bonus
            if context.priority > 5:
                w += 2  # Small boost for high-priority favoring reliable runtimes

            adjusted.append((score, w))

        return adjusted

    # ── Weight Configuration ───────────────────────────────

    def set_weights(
        self,
        performance: float = 0.35,
        reliability: float = 0.40,
        efficiency: float = 0.25,
    ) -> None:
        """Adjust scoring weights. Must sum to ~1.0."""
        self._weights = {
            "performance": performance,
            "reliability": reliability,
            "efficiency": efficiency,
        }
