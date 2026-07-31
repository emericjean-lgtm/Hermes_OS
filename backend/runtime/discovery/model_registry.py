"""Model Registry for the Discovery Engine (HOS-040).

Central registry of known models with discovery status tracking.
Thread-safe.
"""

from __future__ import annotations

import threading
from typing import Optional

from backend.runtime.discovery.discovery_models import (
    BenchmarkResult,
    DiscoverySource,
    ModelInfo,
    ModelStatus,
)


class ModelRegistry:
    """Thread-safe registry of discovered and benchmarked models."""

    def __init__(self, max_models: int = 5000) -> None:
        self._lock = threading.Lock()
        self._models: dict[str, ModelInfo] = {}
        self._benchmarks: dict[str, list[BenchmarkResult]] = {}
        self._max_models = max_models

    # ── Model CRUD ─────────────────────────────────────────

    def register(self, model: ModelInfo) -> None:
        with self._lock:
            self._models[model.model_id] = model

    def get(self, model_id: str) -> Optional[ModelInfo]:
        with self._lock:
            return self._models.get(model_id)

    def get_by_name(self, name: str) -> Optional[ModelInfo]:
        with self._lock:
            for m in self._models.values():
                if m.name == name:
                    return m
        return None

    def list_all(self, status: Optional[ModelStatus] = None) -> list[ModelInfo]:
        with self._lock:
            models = list(self._models.values())
            if status:
                models = [m for m in models if m.status == status]
            return sorted(models, key=lambda m: m.discovered_at, reverse=True)

    def update_status(self, model_id: str, status: ModelStatus) -> bool:
        with self._lock:
            if model_id in self._models:
                self._models[model_id].status = status
                return True
        return False

    def count(self) -> int:
        with self._lock:
            return len(self._models)

    # ── Benchmark Storage ──────────────────────────────────

    def add_benchmark(self, result: BenchmarkResult) -> None:
        with self._lock:
            key = result.model_name
            if key not in self._benchmarks:
                self._benchmarks[key] = []
            self._benchmarks[key].append(result)
            if len(self._benchmarks[key]) > 100:
                self._benchmarks[key] = self._benchmarks[key][-100:]

    def get_benchmarks(self, model_name: str) -> list[BenchmarkResult]:
        with self._lock:
            return list(self._benchmarks.get(model_name, []))

    def get_all_benchmarks(self) -> dict[str, list[BenchmarkResult]]:
        with self._lock:
            return dict(self._benchmarks)

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            by_status = {}
            for m in self._models.values():
                s = m.status.value
                by_status[s] = by_status.get(s, 0) + 1
            return {
                "total_models": len(self._models),
                "total_benchmarks": sum(len(v) for v in self._benchmarks.values()),
                "by_status": by_status,
                "by_source": {
                    src.value: sum(1 for m in self._models.values() if m.source == src)
                    for src in DiscoverySource
                },
            }
