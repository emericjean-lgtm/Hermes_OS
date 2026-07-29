"""Code Intelligence Runtime Scoring (HOS-055D).

Runtime adapter that scores KlaatCode and Oh My Pi as runtime/tool
provider candidates for the Runtime Orchestrator (HOS-038).

Factors considered:
- Historical success rate
- Average task duration
- Resource consumption
- Task complexity match
- Provider availability
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CIRuntimeScore:
    """Scoring result for a code intelligence runtime candidate."""
    provider: str  # "klaatcode" or "ohmypi"
    type: str = "code_intelligence"
    suitability: float = 0.0  # 0.0 - 1.0
    historical_success: float = 0.0
    avg_duration_ms: float = 0.0
    resource_cost: float = 0.0
    available: bool = True
    factors: dict[str, float] = field(default_factory=dict)


class CIRuntimeScorer:
    """Scores KlaatCode and Oh My Pi as runtime candidates.

    Thread-safe. Maintains performance history for adaptive scoring.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._kc_durations: deque[float] = deque(maxlen=100)
        self._omp_durations: deque[float] = deque(maxlen=100)
        self._kc_successes: deque[bool] = deque(maxlen=100)
        self._omp_successes: deque[bool] = deque(maxlen=100)

    def score(
        self,
        task_type: str,
        complexity: float = 0.5,
        klaatcode_available: bool = True,
        ohmypi_available: bool = True,
        context: dict[str, Any] | None = None,
    ) -> list[CIRuntimeScore]:
        """Score both providers for a given task.

        Returns list sorted by suitability descending.
        """
        scores = []

        # KlaatCode
        kc = self._score_provider(
            "klaatcode", task_type, complexity, klaatcode_available,
            self._kc_successes, self._kc_durations, context,
        )
        scores.append(kc)

        # Oh My Pi
        omp = self._score_provider(
            "ohmypi", task_type, complexity, ohmypi_available,
            self._omp_successes, self._omp_durations, context,
        )
        scores.append(omp)

        scores.sort(key=lambda s: s.suitability, reverse=True)
        return scores

    def record_result(
        self, provider: str, success: bool, duration_ms: float
    ) -> None:
        """Record execution result for adaptive scoring."""
        with self._lock:
            if provider == "klaatcode":
                self._kc_successes.append(success)
                self._kc_durations.append(duration_ms)
            elif provider == "ohmypi":
                self._omp_successes.append(success)
                self._omp_durations.append(duration_ms)

    def get_recommendation(
        self, task_type: str, complexity: float = 0.5,
        klaatcode_available: bool = True, ohmypi_available: bool = True,
    ) -> dict[str, Any]:
        """Get a single recommendation with ranking."""
        scores = self.score(task_type, complexity, klaatcode_available, ohmypi_available)
        best = scores[0] if scores else None
        return {
            "recommended": best.provider if best else "none",
            "suitability": round(best.suitability, 4) if best else 0,
            "scores": [
                {"provider": s.provider, "suitability": round(s.suitability, 4)}
                for s in scores
            ],
            "task_type": task_type,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            kc_success = list(self._kc_successes)
            omp_success = list(self._omp_successes)
            kc_dur = list(self._kc_durations)
            omp_dur = list(self._omp_durations)
            return {
                "klaatcode": {
                    "executions": len(kc_success),
                    "success_rate": round(sum(1 for s in kc_success if s) / max(len(kc_success), 1) * 100, 1),
                    "avg_duration_ms": round(sum(kc_dur) / max(len(kc_dur), 1), 1),
                    "min_duration_ms": round(min(kc_dur), 1) if kc_dur else 0,
                    "max_duration_ms": round(max(kc_dur), 1) if kc_dur else 0,
                },
                "ohmypi": {
                    "executions": len(omp_success),
                    "success_rate": round(sum(1 for s in omp_success if s) / max(len(omp_success), 1) * 100, 1),
                    "avg_duration_ms": round(sum(omp_dur) / max(len(omp_dur), 1), 1),
                    "min_duration_ms": round(min(omp_dur), 1) if omp_dur else 0,
                    "max_duration_ms": round(max(omp_dur), 1) if omp_dur else 0,
                },
            }

    # ── Private ──

    def _score_provider(
        self, provider: str, task_type: str, complexity: float,
        available: bool, successes: deque[bool], durations: deque[float],
        context: dict[str, Any] | None,
    ) -> CIRuntimeScore:
        if not available:
            return CIRuntimeScore(provider=provider, suitability=0.0, available=False)

        with self._lock:
            ss = list(successes)
            ds = list(durations)
            hist_success = sum(1 for s in ss if s) / max(len(ss), 1) if ss else 0.80
            avg_dur = sum(ds) / max(len(ds), 1) if ds else 100.0

        # Task type fit
        if provider == "klaatcode":
            task_fit = self._kc_task_fit(task_type)
        else:
            task_fit = self._omp_task_fit(task_type)

        # Resource cost (KlaatCode lighter)
        resource_cost = 0.4 if provider == "klaatcode" else 0.65

        # Context modifiers
        ctx = context or {}
        if ctx.get("requires_lsp") or ctx.get("requires_dap"):
            if provider == "ohmypi":
                task_fit = min(1.0, task_fit + 0.2)
            else:
                task_fit = max(0.0, task_fit - 0.2)

        # Complexity: Oh My Pi handles complex edits better (LSP)
        complexity_mod = 1.0
        if complexity > 0.7:
            if provider == "ohmypi":
                complexity_mod = 1.10
            else:
                complexity_mod = 0.90

        suitability = (
            task_fit * 0.35 +
            hist_success * 0.25 +
            (1.0 - resource_cost) * 0.20 +
            (1.0 - min(avg_dur / 5000, 1.0)) * 0.10 +
            complexity_mod * 0.10
        )

        return CIRuntimeScore(
            provider=provider,
            suitability=round(suitability, 4),
            historical_success=round(hist_success, 4),
            avg_duration_ms=round(avg_dur, 1),
            resource_cost=round(resource_cost, 2),
            available=available,
            factors={
                "task_fit": round(task_fit, 4),
                "historical_success": round(hist_success, 4),
                "resource_cost": resource_cost,
                "complexity_mod": round(complexity_mod, 4),
            },
        )

    @staticmethod
    def _kc_task_fit(task_type: str) -> float:
        kc_strong = {"code_analysis", "architecture_review", "diagnostics", "code_review"}
        kc_medium = {"test_generation", "optimization", "documentation"}
        if task_type in kc_strong:
            return 0.90
        if task_type in kc_medium:
            return 0.65
        return 0.40

    @staticmethod
    def _omp_task_fit(task_type: str) -> float:
        omp_strong = {"refactoring", "debugging", "code_generation"}
        omp_medium = {"code_analysis", "optimization", "code_review"}
        if task_type in omp_strong:
            return 0.90
        if task_type in omp_medium:
            return 0.60
        return 0.35
