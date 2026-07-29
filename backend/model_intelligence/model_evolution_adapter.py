"""Evolution Engine integration for Model Intelligence (HOS-065B).

Connects PerformanceAnalyzer to Evolution Engine for continuous
improvement of model scoring weights and detection of underperforming models.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

from .model_intelligence_models import ModelPerformanceRecord
from .model_profiler import ModelProfiler
from .performance_analyzer import PerformanceAnalyzer


# Default scoring weights
DEFAULT_WEIGHTS = {
    "quality": 0.30,
    "speed": 0.20,
    "reliability": 0.25,
    "resource_efficiency": 0.15,
    "benchmark": 0.10,
}


class ModelEvolutionAdapter:
    """Bridges PerformanceAnalyzer with Evolution Engine (HOS-058)."""

    def __init__(
        self,
        profiler: ModelProfiler | None = None,
        analyzer: PerformanceAnalyzer | None = None,
    ) -> None:
        self._profiler = profiler or ModelProfiler()
        self._analyzer = analyzer or PerformanceAnalyzer()
        self._lock = threading.RLock()
        self._weights = dict(DEFAULT_WEIGHTS)
        self._weight_history: list[dict[str, float]] = []
        self._improvement_suggestions: list[dict[str, Any]] = []

    def get_weights(self) -> dict[str, float]:
        """Get current scoring weights."""
        with self._lock:
            return dict(self._weights)

    def update_weights(self, new_weights: dict[str, float]) -> None:
        """Update scoring weights (called by Evolution Engine)."""
        with self._lock:
            # Clamp each weight between 0.05 and 0.60
            for key in new_weights:
                if key in self._weights:
                    self._weights[key] = max(0.05, min(0.60, new_weights[key]))
            # Normalize to sum to 1.0
            total = sum(self._weights.values())
            if total > 0:
                for key in self._weights:
                    self._weights[key] /= total
            self._weight_history.append(dict(self._weights))
            if len(self._weight_history) > 100:
                self._weight_history.pop(0)

    def analyze_model_performance(self, model_id: str) -> dict[str, Any]:
        """Analyze performance trends for a single model."""
        profile = self._profiler.get_profile(model_id)
        if not profile:
            return {"model_id": model_id, "found": False}

        history = self._profiler.get_performance_history(model_id)
        benchmarks = self._analyzer.get_benchmark_summary(model_id)

        # Calculate trends (history items are dicts from get_performance_history)
        recent = history[-20:] if len(history) > 20 else history
        recent_success = sum(1 for r in recent if r.get("success", False))
        recent_rate = recent_success / max(len(recent), 1)

        older = history[:-20] if len(history) > 20 else []
        older_success = sum(1 for r in older if r.get("success", False))
        older_rate = older_success / max(len(older), 1)

        trend = "stable"
        if len(history) >= 20:
            if recent_rate > older_rate + 0.1:
                trend = "improving"
            elif older_rate > recent_rate + 0.1:
                trend = "degrading"

        avg_duration = sum(r.get("duration_ms", 0) for r in recent) / max(len(recent), 1)

        # Detect underperformance
        needs_attention = recent_rate < 0.7 or trend == "degrading"

        return {
            "model_id": model_id,
            "found": True,
            "total_runs": profile.total_runs,
            "success_rate": profile.success_rate,
            "recent_success_rate": recent_rate,
            "trend": trend,
            "avg_duration_ms": avg_duration,
            "needs_attention": needs_attention,
            "benchmark_count": benchmarks.get("count", 0),
        }

    def detect_underperforming_models(self, threshold: float = 0.7) -> list[dict[str, Any]]:
        """Detect models with success rate below threshold."""
        underperforming = []
        for profile in self._profiler.list_profiles():
            if profile.total_runs >= 5 and profile.success_rate < threshold:
                underperforming.append({
                    "model_id": profile.model_id,
                    "name": profile.name,
                    "success_rate": profile.success_rate,
                    "total_runs": profile.total_runs,
                    "suggestion": "Consider replacement or re-benchmarking",
                })
        return underperforming

    def suggest_model_replacement(self, model_id: str) -> dict[str, Any] | None:
        """Suggest a replacement model for an underperforming one."""
        profile = self._profiler.get_profile(model_id)
        if not profile:
            return None

        # Find better models for the same tasks
        candidates = []
        for other in self._profiler.list_profiles():
            if other.model_id == model_id:
                continue
            if other.vram_required_mb > profile.vram_required_mb * 1.3:
                continue  # Too much VRAM
            if other.overall_score > profile.overall_score * 1.05:
                candidates.append({
                    "model_id": other.model_id,
                    "name": other.name,
                    "overall_score": other.overall_score,
                    "vram_mb": other.vram_required_mb,
                    "score_improvement": round((other.overall_score - profile.overall_score) * 100, 1),
                })

        candidates.sort(key=lambda x: -x["score_improvement"])

        suggestion = {
            "current_model": {"model_id": profile.model_id, "name": profile.name, "score": profile.overall_score},
            "candidates": candidates[:3],
            "reason": f"Success rate {profile.success_rate:.0%} is below threshold",
        }

        with self._lock:
            self._improvement_suggestions.append(suggestion)
            if len(self._improvement_suggestions) > 200:
                self._improvement_suggestions.pop(0)

        return suggestion

    def get_evolution_summary(self) -> dict[str, Any]:
        """Get summary for Evolution Engine consumption."""
        all_models = self._profiler.list_profiles()
        underperforming = self.detect_underperforming_models()
        weight_history = list(self._weight_history)

        return {
            "total_models": len(all_models),
            "underperforming_count": len(underperforming),
            "underperforming_models": underperforming,
            "current_weights": dict(self._weights),
            "weight_evolution": weight_history[-10:] if weight_history else [],
            "model_trends": [self.analyze_model_performance(p.model_id) for p in all_models[:10]],
        }

    def record_execution(self, record: ModelPerformanceRecord) -> None:
        """Record an execution and update profiler."""
        self._profiler.update_performance(record)
