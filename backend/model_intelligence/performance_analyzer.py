"""Performance Analyzer for Hermes OS (HOS-065).

Analyzes model performance from benchmarks, completed missions,
errors, validations, and human satisfaction ratings.
Computes dynamic ModelScore for each model.
"""

from __future__ import annotations

import threading
from typing import Any

from .model_intelligence_models import (
    BenchmarkResult,
    ModelPerformanceRecord,
    ModelProfile,
)


class PerformanceAnalyzer:
    """Analyzes model performance data and computes dynamic scores."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._benchmarks: list[BenchmarkResult] = []
        self._max_history = 1000

    def add_benchmark(self, result: BenchmarkResult) -> None:
        with self._lock:
            self._benchmarks.append(result)
            if len(self._benchmarks) > self._max_history:
                self._benchmarks = self._benchmarks[-self._max_history:]

    def compute_model_score(self, profile: ModelProfile,
                            records: list[ModelPerformanceRecord]) -> float:
        """Compute dynamic ModelScore from all available data."""
        quality = self._compute_quality_score(profile, records)
        speed = self._compute_speed_score(profile)
        reliability = self._compute_reliability_score(records)
        efficiency = self._compute_efficiency_score(profile)
        benchmark = self._compute_benchmark_score(profile.model_id)

        return (
            quality * 0.30
            + speed * 0.20
            + reliability * 0.25
            + efficiency * 0.15
            + benchmark * 0.10
        )

    def compute_quality_score(self, profile: ModelProfile,
                               records: list[ModelPerformanceRecord]) -> float:
        """Public wrapper for quality score computation."""
        return self._compute_quality_score(profile, records)

    def get_benchmark_summary(self, model_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            benchmarks = self._benchmarks
            if model_id:
                benchmarks = [b for b in benchmarks if b.model_id == model_id]

            if not benchmarks:
                return {"count": 0, "avg_latency_ms": 0, "avg_tps": 0, "avg_quality": 0}

            return {
                "count": len(benchmarks),
                "avg_latency_ms": round(sum(b.latency_ms for b in benchmarks) / len(benchmarks), 1),
                "avg_tps": round(sum(b.tokens_per_second for b in benchmarks) / len(benchmarks), 1),
                "avg_quality": round(sum(b.quality_score for b in benchmarks) / len(benchmarks), 3),
                "avg_vram_mb": round(sum(b.vram_usage_mb for b in benchmarks) / len(benchmarks), 0),
            }

    def _compute_quality_score(self, profile: ModelProfile,
                                records: list[ModelPerformanceRecord]) -> float:
        score = 0.5  # Default
        if profile.task_scores:
            score = sum(profile.task_scores.values()) / len(profile.task_scores)
        if records:
            avg_rating = sum(r.human_rating for r in records if r.human_rating > 0)
            rated = sum(1 for r in records if r.human_rating > 0)
            if rated > 0:
                score = (score * 0.6 + (avg_rating / rated) * 0.4)
        return min(1.0, max(0.0, score))

    def _compute_speed_score(self, profile: ModelProfile) -> float:
        tps = profile.tokens_per_second
        if tps >= 80:
            return 1.0
        if tps >= 40:
            return 0.8
        if tps >= 20:
            return 0.6
        if tps >= 10:
            return 0.4
        return 0.2 if tps > 0 else 0.0

    def _compute_reliability_score(self, records: list[ModelPerformanceRecord]) -> float:
        if not records:
            return 0.5
        successes = sum(1 for r in records if r.success)
        return successes / len(records)

    def _compute_efficiency_score(self, profile: ModelProfile) -> float:
        if profile.vram_required_mb == 0:
            return 0.5
        # Lower VRAM = higher efficiency (80GB = 0, 2GB = 1)
        return max(0.0, 1.0 - (profile.vram_required_mb / 80000.0))

    def _compute_benchmark_score(self, model_id: str) -> float:
        relevant = [b for b in self._benchmarks if b.model_id == model_id]
        if not relevant:
            return 0.5
        avg_quality = sum(b.quality_score for b in relevant) / len(relevant)
        return min(1.0, avg_quality * 1.2)  # Slight boost for benchmarked models

    def _compute_success_rate(self, records: list[ModelPerformanceRecord]) -> float:
        if not records:
            return 0.0
        return sum(1 for r in records if r.success) / len(records)
