"""Optimization Engine — improves execution patterns across missions."""

from __future__ import annotations

import threading
from typing import Any

from .execution_models import OptimizationCategory


class OptimizationEngine:
    """Post-hoc optimization engine that identifies inefficiencies across executions.

    Identifies: slow tasks, bad runtime choices, wrong skills, inefficient tools.
    Produces: recommendations, new patterns, improved strategies.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._observations: list[dict[str, Any]] = []  # Historical observations
        self._recommendations: dict[str, list[str]] = {}  # category → recs

    def record_execution(self, execution_id: str, metrics: dict[str, Any]) -> None:
        """Record execution metrics for pattern analysis."""
        with self._lock:
            self._observations.append({
                "execution_id": execution_id,
                **metrics,
            })

    def identify_slow_tasks(self) -> list[dict[str, Any]]:
        """Find tasks consistently running slower than expected."""
        with self._lock:
            slow = []
            for obs in self._observations:
                if obs.get("duration_ratio", 0) > 2.0:
                    slow.append({
                        "execution_id": obs["execution_id"],
                        "task": obs.get("task_name", "unknown"),
                        "actual_ms": obs.get("duration_ms", 0),
                        "expected_ms": obs.get("expected_ms", 0),
                    })
            return slow[:10]

    def identify_runtime_issues(self) -> list[dict[str, Any]]:
        """Identify runtime selections that consistently underperform."""
        with self._lock:
            runtime_stats: dict[str, list[float]] = {}
            for obs in self._observations:
                rt = obs.get("runtime_id", "unknown")
                duration = obs.get("duration_ms", 0)
                runtime_stats.setdefault(rt, []).append(duration)

            issues = []
            for rt, durations in runtime_stats.items():
                if len(durations) >= 2:
                    avg = sum(durations) / len(durations)
                    if avg > 10_000:  # 10 seconds threshold
                        issues.append({"runtime_id": rt, "avg_duration_ms": avg, "runs": len(durations)})
            return issues

    def generate_recommendations(self) -> list[dict[str, Any]]:
        """Generate actionable recommendations from observed data."""
        with self._lock:
            recs = []
            slow = self.identify_slow_tasks()
            if slow:
                recs.append({
                    "category": OptimizationCategory.SCHEDULE.value,
                    "recommendation": "Consider increasing parallelism for slow tasks.",
                    "affected": [s["task"] for s in slow],
                })

            runtime_issues = self.identify_runtime_issues()
            if runtime_issues:
                recs.append({
                    "category": OptimizationCategory.RUNTIME.value,
                    "recommendation": "Some runtimes are consistently slow — consider fallback alternatives.",
                    "affected": [r["runtime_id"] for r in runtime_issues],
                })

            return recs

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "observations": len(self._observations),
                "recommendations_count": sum(len(v) for v in self._recommendations.values()),
                "slow_tasks": len(self.identify_slow_tasks()),
                "runtime_issues": len(self.identify_runtime_issues()),
            }
