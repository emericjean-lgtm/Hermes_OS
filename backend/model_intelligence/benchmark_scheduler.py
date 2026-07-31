"""Benchmark Scheduler for Hermes OS (HOS-065).

Automatically schedules periodic benchmarks, compares models,
detects regressions, and discovers new models.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .model_intelligence_models import (
    BenchmarkResult,
    ModelProfile,
    TaskType,
)
from .model_profiler import ModelProfiler
from .performance_analyzer import PerformanceAnalyzer

logger = logging.getLogger(__name__)


class BenchmarkScheduler:
    """Schedules and manages model benchmarks."""

    def __init__(self, profiler: ModelProfiler | None = None,
                 analyzer: PerformanceAnalyzer | None = None) -> None:
        self._profiler = profiler or ModelProfiler()
        self._analyzer = analyzer or PerformanceAnalyzer()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._scheduled_benchmarks: list[dict[str, Any]] = []
        self._regression_history: list[dict[str, Any]] = []

    def start(self, interval_h: int = 24) -> None:
        """Start periodic benchmarking."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, args=(interval_h,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def run_benchmark(self, model_id: str, task_type: TaskType) -> BenchmarkResult:
        """Run a single benchmark for a model on a specific task."""
        profile = self._profiler.get_profile(model_id)
        if not profile:
            raise ValueError(f"Unknown model: {model_id}")

        # Simulate benchmark execution
        latency = self._simulate_latency(profile)
        tps = profile.tokens_per_second * random.uniform(0.85, 1.15)
        vram = profile.vram_required_mb * random.uniform(0.8, 1.2)
        quality = profile.task_scores.get(task_type.value, 0.5) * random.uniform(0.9, 1.1)

        result = BenchmarkResult(
            benchmark_id=f"bm_{int(time.time())}_{model_id[:8]}",
            model_id=model_id,
            task_type=task_type,
            latency_ms=round(latency, 1),
            tokens_per_second=round(tps, 1),
            vram_usage_mb=int(vram),
            ram_usage_mb=int(profile.ram_required_mb * random.uniform(0.7, 1.0)),
            quality_score=round(min(1.0, quality), 3),
            temperature=0.2,
        )

        self._analyzer.add_benchmark(result)

        # Check for regression
        self._check_regression(result, profile)

        return result

    def run_full_benchmark(self, task_types: list[TaskType] | None = None) -> list[BenchmarkResult]:
        """Benchmark all models on all specified task types."""
        if task_types is None:
            task_types = list(TaskType)

        profiles = self._profiler.list_profiles()
        results = []
        for profile in profiles:
            for task_type in task_types:
                try:
                    result = self.run_benchmark(profile.model_id, task_type)
                    results.append(result)
                except ValueError:
                    continue
        return results

    def get_latest_benchmarks(self, model_id: str | None = None,
                               limit: int = 20) -> list[dict[str, Any]]:
        # Simulated latest benchmarks
        benchmarks = []
        profiles = self._profiler.list_profiles()
        for profile in profiles[:3]:
            for task_type in list(TaskType)[:3]:
                bm = BenchmarkResult(
                    benchmark_id=f"bm_{profile.model_id[:8]}_{task_type.value[:4]}",
                    model_id=profile.model_id,
                    task_type=task_type,
                    latency_ms=random.uniform(50, 500),
                    tokens_per_second=profile.tokens_per_second * random.uniform(0.9, 1.1),
                    vram_usage_mb=int(profile.vram_required_mb * random.uniform(0.8, 1.0)),
                    ram_usage_mb=int(profile.ram_required_mb * random.uniform(0.7, 0.9)),
                    quality_score=profile.task_scores.get(task_type.value, 0.5) * random.uniform(0.95, 1.05),
                    temperature=0.2,
                )
                benchmarks.append({
                    "benchmark_id": bm.benchmark_id,
                    "model_id": bm.model_id,
                    "task_type": bm.task_type.value,
                    "latency_ms": bm.latency_ms,
                    "tokens_per_second": bm.tokens_per_second,
                    "vram_usage_mb": bm.vram_usage_mb,
                    "quality_score": bm.quality_score,
                })
        return benchmarks[:limit]

    def get_regressions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return self._regression_history[-limit:]

    def _loop(self, interval_h: int) -> None:
        while self._running:
            try:
                self.run_full_benchmark()
            except Exception:
                logger.warning("Benchmark run failed", exc_info=True)
            time.sleep(interval_h * 3600)

    def _simulate_latency(self, profile: ModelProfile) -> float:
        base = profile.latency_ms if profile.latency_ms > 0 else 200.0
        return base * random.uniform(0.8, 1.2)

    def _check_regression(self, result: BenchmarkResult,
                          profile: ModelProfile) -> None:
        expected_q = profile.task_scores.get(result.task_type.value, 0.5)
        if result.quality_score < expected_q * 0.7:
            regression = {
                "model_id": result.model_id,
                "task_type": result.task_type.value,
                "previous_score": expected_q,
                "current_score": result.quality_score,
                "drop_pct": round((1 - result.quality_score / expected_q) * 100, 1),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with self._lock:
                self._regression_history.append(regression)
