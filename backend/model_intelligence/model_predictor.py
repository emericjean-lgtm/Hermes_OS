"""Model Predictor for Hermes OS (HOS-065).

Predicts model performance for tasks based on historical data,
model profiles, and task characteristics.
"""

from __future__ import annotations

import threading
from typing import Any

from .model_intelligence_models import (
    BenchmarkResult,
    ModelPerformanceRecord,
    ModelProfile,
    TaskContext,
    TaskType,
)


class ModelPredictor:
    """Predicts model performance for specific tasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._predictions: list[dict[str, Any]] = []

    def predict_latency(self, profile: ModelProfile,
                        task: TaskContext) -> float:
        base_latency = profile.latency_ms if profile.latency_ms > 0 else 100.0
        complexity_factor = 1.0 + (task.complexity * 2.0)
        return base_latency * complexity_factor

    def predict_tokens_per_second(self, profile: ModelProfile,
                                   task: TaskContext) -> float:
        tps = profile.tokens_per_second
        if tps == 0:
            tps = self._estimate_tps(profile)
        complexity_penalty = 1.0 - (task.complexity * 0.3)
        return tps * max(0.5, complexity_penalty)

    def predict_success_probability(self, profile: ModelProfile,
                                     records: list[ModelPerformanceRecord],
                                     task: TaskContext) -> float:
        if records:
            success_rate = sum(1 for r in records if r.success) / len(records)
        else:
            success_rate = profile.historical_success_rate or 0.5
        task_fit = profile.task_scores.get(task.task_type.value, 0.5)
        return min(1.0, (success_rate * 0.6 + task_fit * 0.4))

    def predict_vram_usage(self, profile: ModelProfile,
                            task: TaskContext) -> int:
        base_vram = profile.vram_required_mb
        context_mult = min(2.0, task.complexity + 1.0)
        return int(base_vram * context_mult)

    def rank_models(self, profiles: list[ModelProfile],
                     records: list[ModelPerformanceRecord],
                     task: TaskContext) -> list[dict[str, Any]]:
        scored = []
        for profile in profiles:
            latency = self.predict_latency(profile, task)
            tps = self.predict_tokens_per_second(profile, task)
            success_prob = self.predict_success_probability(profile, records, task)
            vram = self.predict_vram_usage(profile, task)

            if vram > task.max_vram_mb:
                continue
            if latency > task.max_latency_ms:
                continue

            task_score = profile.task_scores.get(task.task_type.value, 0.5)
            overall = task_score * 0.35 + success_prob * 0.35 + (tps / 100.0) * 0.15 + (1.0 - vram / task.max_vram_mb) * 0.15

            scored.append({
                "model_id": profile.model_id,
                "name": profile.name,
                "score": round(overall, 3),
                "confidence": round(success_prob, 3),
                "estimated_latency_ms": int(latency),
                "estimated_tps": round(tps, 1),
                "estimated_vram_mb": vram,
                "task_score": round(task_score, 3),
                "parameters_b": profile.parameters_b,
                "reason": self._generate_reason(profile, task_score, success_prob, vram),
            })

        scored.sort(key=lambda x: -x["score"])
        return scored

    def _estimate_tps(self, profile: ModelProfile) -> float:
        params = profile.parameters_b
        if params <= 3:
            return 80.0
        if params <= 7:
            return 50.0
        if params <= 14:
            return 35.0
        if params <= 30:
            return 25.0
        if params <= 70:
            return 15.0
        return 8.0

    def _generate_reason(self, profile: ModelProfile, task_score: float,
                         success_prob: float, vram: int) -> str:
        parts = []
        if task_score > 0.85:
            parts.append(f"Excellent task fit ({task_score:.0%})")
        elif task_score > 0.7:
            parts.append(f"Good task fit ({task_score:.0%})")
        if success_prob > 0.85:
            parts.append(f"High reliability ({success_prob:.0%})")
        if vram <= 4000:
            parts.append("Low VRAM footprint")
        return " · ".join(parts) if parts else "Reasonable choice"

    def log_prediction(self, model_id: str, task_type: str,
                        confidence: float, selected: bool) -> None:
        self._predictions.append({
            "model_id": model_id,
            "task_type": task_type,
            "confidence": confidence,
            "selected": selected,
        })
        if len(self._predictions) > 500:
            self._predictions = self._predictions[-500:]

    def get_prediction_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._predictions[-limit:]
