"""Model Profiler for Hermes OS (HOS-065).

Creates and manages profiles for all available models,
tracking performance, resource usage, and task suitability.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .model_intelligence_models import (
    ModelArchitecture,
    ModelPerformanceRecord,
    ModelProfile,
    PREDEFINED_MODELS,
    Quantization,
    RuntimeBackend,
    TaskType,
)


class ModelProfiler:
    """Creates, updates, and manages model performance profiles."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: dict[str, ModelProfile] = {}
        self._performance_history: list[ModelPerformanceRecord] = []
        self._max_history = 1000
        self._load_predefined()

    def _load_predefined(self) -> None:
        for model_id, data in PREDEFINED_MODELS.items():
            arch = ModelArchitecture(data.get("architecture", "other"))
            quant = Quantization(data.get("quantization", "q4_k_m"))
            backends = [RuntimeBackend(b) for b in data.get("available_backends", ["ollama"])]
            task_scores = data.get("task_scores", {})

            profile = ModelProfile(
                model_id=model_id,
                name=data.get("name", model_id),
                architecture=arch,
                parameters_b=data.get("parameters_b", 0.0),
                quantization=quant,
                vram_required_mb=data.get("vram_required_mb", 0),
                ram_required_mb=data.get("ram_required_mb", 0),
                context_window=data.get("context_window", 4096),
                tokens_per_second=data.get("tokens_per_second", 0.0),
                task_scores=task_scores,
                available_backends=backends,
                tags=data.get("tags", []),
            )
            self._profiles[model_id] = profile

    def register_model(self, profile: ModelProfile) -> None:
        with self._lock:
            self._profiles[profile.model_id] = profile

    def get_profile(self, model_id: str) -> ModelProfile | None:
        with self._lock:
            return self._profiles.get(model_id)

    def list_profiles(self) -> list[ModelProfile]:
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: -p.overall_score)

    def update_performance(self, record: ModelPerformanceRecord) -> None:
        with self._lock:
            self._performance_history.append(record)
            if len(self._performance_history) > self._max_history:
                self._performance_history = self._performance_history[-self._max_history:]

            profile = self._profiles.get(record.model_id)
            if profile:
                profile.total_runs += 1
                if record.success:
                    profile.successful_runs += 1
                profile.historical_success_rate = (
                    profile.successful_runs / profile.total_runs
                ) if profile.total_runs > 0 else 0.0
                profile.last_used = datetime.now(timezone.utc).isoformat()

    def get_models_for_task(self, task_type: TaskType,
                            max_vram_mb: int = 8192,
                            min_quality: float = 0.3) -> list[ModelProfile]:
        with self._lock:
            suitable = []
            for profile in self._profiles.values():
                if profile.vram_required_mb > max_vram_mb:
                    continue
                task_score = profile.task_scores.get(task_type.value, 0.5)
                if task_score < min_quality:
                    continue
                suitable.append(profile)
            return sorted(suitable, key=lambda p: -p.task_scores.get(task_type.value, 0.0))

    def get_top_models(self, task_type: TaskType | None = None,
                       limit: int = 5) -> list[ModelProfile]:
        with self._lock:
            profiles = list(self._profiles.values())
            if task_type:
                profiles = [p for p in profiles
                           if task_type.value in p.task_scores]
            return sorted(profiles, key=lambda p: -p.overall_score)[:limit]

    def get_performance_history(self, model_id: str | None = None,
                                 limit: int = 100) -> list[dict[str, Any]]:
        records = self._performance_history
        if model_id:
            records = [r for r in records if r.model_id == model_id]
        return [
            {
                "model_id": r.model_id,
                "task_type": r.task_type.value,
                "duration_ms": r.duration_ms,
                "tokens_used": r.tokens_used,
                "success": r.success,
                "human_rating": r.human_rating,
                "error_type": r.error_type,
                "timestamp": r.timestamp,
            }
            for r in records[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_models = len(self._profiles)
            total_runs = sum(p.total_runs for p in self._profiles.values())
            avg_success = (
                sum(p.success_rate for p in self._profiles.values()) / total_models
            ) if total_models > 0 else 0.0
            return {
                "total_models": total_models,
                "total_runs": total_runs,
                "average_success_rate": round(avg_success, 3),
                "models": [
                    {
                        "id": p.model_id,
                        "name": p.name,
                        "parameters_b": p.parameters_b,
                        "vram_mb": p.vram_required_mb,
                        "tps": p.tokens_per_second,
                        "score": round(p.overall_score, 3),
                        "success_rate": round(p.success_rate, 3),
                    }
                    for p in sorted(self._profiles.values(), key=lambda x: -x.overall_score)
                ],
            }
