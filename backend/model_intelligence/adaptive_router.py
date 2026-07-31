"""Adaptive Model Router for Hermes OS (HOS-065).

Selects the best model, runtime, and configuration for each task
based on model profiles, performance history, and resource constraints.
"""

from __future__ import annotations

import threading
from typing import Any

from .model_intelligence_models import (
    ModelDecision,
    ModelPerformanceRecord,
    ModelProfile,
    Quantization,
    RuntimeBackend,
    TaskContext,
    TaskType,
)
from .model_predictor import ModelPredictor
from .model_profiler import ModelProfiler
from .performance_analyzer import PerformanceAnalyzer


class AdaptiveRouter:
    """Intelligently routes tasks to optimal models and runtimes."""

    def __init__(self, profiler: ModelProfiler | None = None,
                 analyzer: PerformanceAnalyzer | None = None,
                 predictor: ModelPredictor | None = None) -> None:
        self._profiler = profiler or ModelProfiler()
        self._analyzer = analyzer or PerformanceAnalyzer()
        self._predictor = predictor or ModelPredictor()
        self._lock = threading.RLock()
        self._decisions: list[ModelDecision] = []
        self._max_history = 500

    def recommend(self, task: TaskContext) -> ModelDecision:
        """Recommend the best model for a given task context."""
        profiles = self._profiler.list_profiles()
        records = self._get_records_for_task(task.task_type)

        # Filter by VRAM
        viable = [p for p in profiles if p.vram_required_mb <= task.max_vram_mb]

        if not viable:
            # Fallback: find the smallest model that can fit
            viable = sorted(profiles, key=lambda p: p.vram_required_mb)
            if not viable:
                return self._fallback_decision(task)

        # Rank using predictor
        ranked = self._predictor.rank_models(viable, records, task)
        if not ranked:
            return self._fallback_decision(task)

        best = ranked[0]
        profile = self._profiler.get_profile(best["model_id"])
        runtime = self._select_runtime(profile, task)
        quantization = self._select_quantization(profile, task)

        alternatives = []
        for alt in ranked[1:4]:
            alternatives.append({
                "model_id": alt["model_id"],
                "name": alt["name"],
                "score": alt["score"],
                "reason": alt.get("reason", ""),
            })

        decision = ModelDecision(
            model_id=best["model_id"],
            model_name=best["name"],
            runtime=runtime,
            quantization=quantization,
            confidence=best["confidence"],
            reason=best["reason"],
            alternatives=alternatives,
            estimated_latency_ms=best["estimated_latency_ms"],
            estimated_tokens_per_second=best["estimated_tps"],
            estimated_vram_mb=best["estimated_vram_mb"],
            task_context=task,
        )

        self._log_decision(decision)
        return decision

    def recommend_for_text(self, task_description: str,
                           language: str = "python",
                           max_vram_mb: int = 8192) -> ModelDecision:
        """Recommend model from a text description of the task."""
        task_type = self._infer_task_type(task_description)
        complexity = self._infer_complexity(task_description)
        task = TaskContext(
            task_type=task_type,
            complexity=complexity,
            language=language,
            max_vram_mb=max_vram_mb,
        )
        return self.recommend(task)

    def _select_runtime(self, profile: ModelProfile | None,
                        task: TaskContext) -> RuntimeBackend:
        if not profile or not profile.available_backends:
            return RuntimeBackend.OLLAMA
        backends = profile.available_backends
        if task.priority == "high" and RuntimeBackend.VLLM in backends:
            return RuntimeBackend.VLLM
        if task.requires_reasoning and RuntimeBackend.KTRANSFORMERS in backends:
            return RuntimeBackend.KTRANSFORMERS
        return backends[0]

    def _select_quantization(self, profile: ModelProfile | None,
                              task: TaskContext) -> Quantization:
        if not profile:
            return Quantization.Q4_K_M
        if task.max_vram_mb < profile.vram_required_mb * 0.7:
            return Quantization.Q4_0
        if task.max_vram_mb < profile.vram_required_mb * 0.9:
            return Quantization.Q4_K_M
        if task.priority == "high":
            return Quantization.F16
        return Quantization.Q5_K_M

    def _infer_task_type(self, text: str) -> TaskType:
        text_lower = text.lower()
        # More specific intents first (order matters for keyword overlap)
        if any(w in text_lower for w in ["debug", "bug", "fix", "error", "erreur"]):
            return TaskType.DEBUG
        if any(w in text_lower for w in ["refactor", "restructure", "clean up", "clean"]):
            return TaskType.REFACTOR
        if any(w in text_lower for w in ["review", "revue", "vérifie", "check"]):
            return TaskType.CODE_REVIEW
        if any(w in text_lower for w in ["reason", "pense", "réfléchis", "logic"]):
            return TaskType.REASONING
        if any(w in text_lower for w in ["analyse", "analyze", "explain", "comprendre"]):
            return TaskType.ANALYSIS
        if any(w in text_lower for w in ["optimise", "optimize", "performance"]):
            return TaskType.OPTIMIZATION
        if any(w in text_lower for w in ["document", "doc", "readme"]):
            return TaskType.DOCUMENTATION
        if any(w in text_lower for w in ["write", "create", "generate", "implement",
                                          "codage", "crée", "écris", "code"]):
            return TaskType.CODE_GENERATION
        if any(w in text_lower for w in ["chat", "discute", "parle", "question"]):
            return TaskType.CHAT
        return TaskType.GENERAL

    def _infer_complexity(self, text: str) -> float:
        words = len(text.split())
        if words > 30:
            return 0.8
        if words > 15:
            return 0.5
        return 0.3

    def _get_records_for_task(self, task_type: TaskType) -> list[ModelPerformanceRecord]:
        return []

    def _fallback_decision(self, task: TaskContext) -> ModelDecision:
        return ModelDecision(
            model_id="llama3.2-3b",
            model_name="Llama 3.2 3B (fallback)",
            runtime=RuntimeBackend.OLLAMA,
            quantization=Quantization.Q4_K_M,
            confidence=0.5,
            reason="No optimal model found, using lightweight fallback",
            alternatives=[],
            estimated_vram_mb=2000,
            task_context=task,
        )

    def _log_decision(self, decision: ModelDecision) -> None:
        self._decisions.append(decision)
        if len(self._decisions) > self._max_history:
            self._decisions = self._decisions[-self._max_history:]

    def get_decision_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            {
                "model_id": d.model_id,
                "model_name": d.model_name,
                "runtime": d.runtime.value,
                "confidence": d.confidence,
                "reason": d.reason,
                "estimated_latency_ms": d.estimated_latency_ms,
            }
            for d in self._decisions[-limit:]
        ]
