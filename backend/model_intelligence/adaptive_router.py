"""Adaptive Model Router for Hermes OS (HOS-065).

Selects the best model, runtime, and configuration for each task
based on model profiles, performance history, and resource constraints.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

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
from .model_runtime_optimizer import ModelRuntimeOptimizer
from .performance_analyzer import PerformanceAnalyzer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudGate:
    """What AdaptiveRouter needs to consider a cloud (OpenRouter free-model)
    escalation, injected so it never depends on Aegis or OpenRouter directly
    — see ``set_cloud()`` and model_intelligence/routes.py's ``_get_router()``.

    ``authorized``/``has_quota`` are cheap/cached by the caller (Aegis's
    evaluate() is pure/local; CloudModelCatalog.has_budget() caches its own
    /key check) — recommend() may call either once per candidate task, so
    neither should perform a slow network call directly. ``refresh_catalog``
    is the one call allowed to be slow the *first* time (CloudModelCatalog's
    own TTL makes every call after that a no-op) — deliberately triggered
    from here, on first real cloud-eligible recommendation, rather than
    blocking process bootstrap for a discovery call that a purely-local
    deployment would never need.
    """

    authorized: Callable[[], bool]
    has_quota: Callable[[], bool]
    refresh_catalog: Callable[[], None]


class AdaptiveRouter:
    """Intelligently routes tasks to optimal models and runtimes."""

    def __init__(self, profiler: ModelProfiler | None = None,
                 analyzer: PerformanceAnalyzer | None = None,
                 predictor: ModelPredictor | None = None,
                 cloud: CloudGate | None = None,
                 runtime_optimizer: ModelRuntimeOptimizer | None = None) -> None:
        self._profiler = profiler or ModelProfiler()
        self._analyzer = analyzer or PerformanceAnalyzer()
        self._predictor = predictor or ModelPredictor()
        self._cloud = cloud
        self._runtime_optimizer = runtime_optimizer
        self._lock = threading.RLock()
        self._decisions: list[ModelDecision] = []
        self._max_history = 500

    def set_cloud(self, cloud: CloudGate | None) -> None:
        """Wire (or clear) cloud escalation after construction — mirrors the
        set_model_adapter()/set_runtime_orchestrator() pattern the bootstrap
        already uses elsewhere. None (the default) keeps recommend() 100%
        local, unchanged from before this feature existed."""
        self._cloud = cloud

    def set_runtime_optimizer(self, runtime_optimizer: ModelRuntimeOptimizer | None) -> None:
        """Wire (or clear) the real model+runtime+quantization co-optimizer
        (HOS-071 Phase D). ModelRuntimeOptimizer already existed with real,
        working combinatorial scoring across every viable runtime/
        quantization pair — it was simply never consulted by recommend(),
        which picked runtime and quantization with two small, independent
        heuristics instead (_select_runtime/_select_quantization below).
        None (the default) keeps those heuristics, unchanged."""
        self._runtime_optimizer = runtime_optimizer

    def recommend(self, task: TaskContext, *, allow_cloud: bool = True) -> ModelDecision:
        """Recommend the best model for a given task context.

        Local-first by construction: a cloud (OpenRouter free-model) profile
        is only even considered when no local model is viable for this task,
        or the task explicitly opted in (``task.cloud_escalation_allowed`` —
        mirrors how reasoning_escalation/advanced_analysis are deliberate,
        named local tiers rather than something a heuristic silently
        triggers). Even then, cloud is used only if Aegis authorizes it and
        real quota remains right now — otherwise this falls straight through
        to the same local ranking as before, which is the automatic
        cloud-exhausted-or-unauthorized -> local fallback.
        """
        # chat_capable excludes embedding-only models (nomic-embed-text):
        # Ollama's /api/chat returns 400 for them. Found by actually running
        # a mission through this recommendation end to end — every other
        # ranking signal starts at its neutral untrained default, so the
        # smallest-VRAM embedding model was winning every single time.
        local_profiles = [p for p in self._profiler.list_profiles()
                          if p.chat_capable and RuntimeBackend.OPENROUTER not in p.available_backends]
        records = self._get_records_for_task(task.task_type)

        # Filter by VRAM — local candidates only; cloud profiles carry no
        # local VRAM cost and are ranked separately below.
        local_viable = [p for p in local_profiles if p.vram_required_mb <= task.max_vram_mb]

        cloud_eligible = allow_cloud and self._cloud is not None and (
            not local_viable or task.cloud_escalation_allowed
        )
        if cloud_eligible:
            cloud_decision = self._try_cloud_recommendation(
                task, records, no_local_viable=not local_viable,
            )
            if cloud_decision is not None:
                self._log_decision(cloud_decision)
                return cloud_decision
            # Cloud unavailable right now (unauthorized, no quota, or no
            # cloud profiles registered) — fall through to local exactly as
            # if allow_cloud had been False. This is the automatic
            # cloud-exhausted -> local fallback requirement.

        viable = local_viable
        if not viable:
            # Fallback: find the smallest local model that can fit
            viable = sorted(local_profiles, key=lambda p: p.vram_required_mb)
            if not viable:
                return self._fallback_decision(task)

        # Rank using predictor
        ranked = self._predictor.rank_models(viable, records, task)
        if not ranked:
            return self._fallback_decision(task)

        best = ranked[0]
        profile = self._profiler.get_profile(best["model_id"])
        runtime, quantization = self._select_runtime_and_quantization(profile, task)

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
            num_ctx=profile.context_window if profile else 0,
        )

        self._log_decision(decision)
        return decision

    def _try_cloud_recommendation(
        self, task: TaskContext, records: list[ModelPerformanceRecord],
        *, no_local_viable: bool,
    ) -> ModelDecision | None:
        """None means "cloud isn't a real option right now" — every caller
        treats that as "fall through to local", never as an error."""
        assert self._cloud is not None
        try:
            # The one call here allowed to be slow the first time — see
            # CloudGate's docstring. Read profiles fresh afterwards (not a
            # snapshot from before this call) so a first-time discovery is
            # actually visible to this same recommendation.
            self._cloud.refresh_catalog()
        except Exception:
            logger.debug("cloud catalogue refresh failed", exc_info=True)

        cloud_profiles = [p for p in self._profiler.list_profiles()
                          if p.chat_capable and RuntimeBackend.OPENROUTER in p.available_backends]
        if not cloud_profiles:
            return None
        try:
            if not self._cloud.authorized():
                return None
            if not self._cloud.has_quota():
                return None
        except Exception:
            # A broken gate must not crash recommend() — it must behave as
            # if cloud were simply unavailable, same as no quota/no auth.
            return None

        ranked = self._predictor.rank_models(cloud_profiles, records, task)
        if not ranked:
            return None

        best = ranked[0]
        profile = self._profiler.get_profile(best["model_id"])
        alternatives = [
            {"model_id": alt["model_id"], "name": alt["name"],
             "score": alt["score"], "reason": alt.get("reason", "")}
            for alt in ranked[1:4]
        ]
        reason = best.get("reason") or "task fit"
        why = "no local model was viable" if no_local_viable else "task opted in"
        return ModelDecision(
            model_id=best["model_id"],
            model_name=best["name"],
            runtime=RuntimeBackend.OPENROUTER,
            quantization=Quantization.NONE,
            confidence=best["confidence"],
            reason=f"cloud escalation ({reason}) — {why}",
            alternatives=alternatives,
            estimated_latency_ms=best["estimated_latency_ms"],
            estimated_tokens_per_second=best["estimated_tps"],
            estimated_vram_mb=0,
            task_context=task,
            num_ctx=profile.context_window if profile else 0,
        )

    def recommend_for_text(self, task_description: str,
                           language: str = "python",
                           max_vram_mb: int = 8192,
                           *, allow_cloud: bool = True,
                           task_type_hint: TaskType | str | None = None) -> ModelDecision:
        """Recommend model from a text description of the task.

        ``task_type_hint``: a caller-supplied, already-structured task type
        (e.g. a mission node's own ``type`` field, HOS-070) takes priority
        over re-inferring one from keyword-matching ``task_description`` —
        found via audit that a real, more precise signal existed and was
        silently discarded in favour of a weaker one. Falls back to keyword
        inference when absent or unrecognised, unchanged from before.
        """
        if task_type_hint:
            try:
                task_type = (task_type_hint if isinstance(task_type_hint, TaskType)
                            else TaskType(task_type_hint))
            except ValueError:
                task_type = self._infer_task_type(task_description)
        else:
            task_type = self._infer_task_type(task_description)
        complexity = self._infer_complexity(task_description)
        task = TaskContext(
            task_type=task_type,
            complexity=complexity,
            language=language,
            max_vram_mb=max_vram_mb,
        )
        return self.recommend(task, allow_cloud=allow_cloud)

    def _select_runtime_and_quantization(
        self, profile: ModelProfile | None, task: TaskContext,
    ) -> tuple[RuntimeBackend, Quantization]:
        """The real combinatorial search (HOS-071 Phase D) when
        ModelRuntimeOptimizer is wired — every viable runtime/quantization
        pair, scored together against this task's real VRAM ceiling, not
        two independent single-shot heuristics guessing at each dimension
        separately. Falls back to those heuristics when unwired (bare
        construction, hermetic tests) or when the optimizer finds nothing
        viable (e.g. profile has no available_backends registered)."""
        if self._runtime_optimizer is not None and profile is not None:
            best = self._runtime_optimizer.get_best(
                profile, task, system_vram_mb=task.max_vram_mb, has_gpu=True,
            )
            if best is not None:
                return best.runtime, best.quantization
        return self._select_runtime(profile, task), self._select_quantization(profile, task)

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
        # This named a fixed model_id ("llama3.2-3b") that has never been
        # installed in any deployment of this project — the one path meant
        # to always succeed recommended a model that could not run. The
        # lightest *real*, chat-capable profile the profiler actually knows
        # about (from config/models.yaml) is the honest fallback: still real
        # if nothing scored above the caller's constraints. chat_capable
        # matters here too — this path is exactly as reachable as recommend()'s
        # main path when every candidate is filtered out by VRAM/latency.
        # Local only, deliberately: this path hardcodes runtime=OLLAMA below
        # (it is the "nothing else worked" floor, not another cloud gate), and
        # every cloud profile carries vram_required_mb=0, which would win
        # min() outright and silently skip the auth/quota checks recommend()
        # otherwise always applies before choosing a cloud model.
        profiles = [p for p in self._profiler.list_profiles()
                   if p.chat_capable and RuntimeBackend.OPENROUTER not in p.available_backends]
        lightest = min(profiles, key=lambda p: p.vram_required_mb) if profiles else None

        return ModelDecision(
            model_id=lightest.model_id if lightest else "",
            model_name=f"{lightest.name} (fallback)" if lightest else "no model available",
            runtime=RuntimeBackend.OLLAMA,
            quantization=Quantization.Q4_K_M,
            confidence=0.5 if lightest else 0.0,
            reason="No optimal model found, using the lightest known profile"
                   if lightest else "No model profiles are registered",
            alternatives=[],
            estimated_vram_mb=lightest.vram_required_mb if lightest else 0,
            task_context=task,
            num_ctx=lightest.context_window if lightest else 0,
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
