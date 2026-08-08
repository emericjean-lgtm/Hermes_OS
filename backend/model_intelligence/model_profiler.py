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
    _infer_architecture,
    _infer_parameters_b,
)
from .performance_analyzer import PerformanceAnalyzer


class ModelProfiler:
    """Creates, updates, and manages model performance profiles."""

    def __init__(self, analyzer: Any = None) -> None:
        """``analyzer`` (a PerformanceAnalyzer, HOS-071 Phase B): ranking
        (list_profiles/get_top_models) always sorts by its
        compute_model_score() — the one formula that matches the documented
        Quality/Reliability/Speed/Efficiency/Benchmark weights — rather than
        ModelProfile.overall_score's own, separately-maintained property,
        whose per-factor math reads different data (e.g. reliability from
        this profiler's own history vs. success_rate, benchmark from a
        benchmarks list vs. a static field) and can diverge from
        compute_model_score even at identical weights. None (the default)
        builds a private PerformanceAnalyzer rather than falling back to
        that property — callers who share the container's real analyzer
        (routes.py's _get_profiler()) get its real benchmark history too;
        callers who don't (bare construction in tests/other adapters) still
        get the one correct formula, just without cross-model benchmark
        data to draw on."""
        self._lock = threading.RLock()
        self._profiles: dict[str, ModelProfile] = {}
        self._performance_history: list[ModelPerformanceRecord] = []
        self._max_history = 1000
        self._analyzer = analyzer or PerformanceAnalyzer()
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
                chat_capable=data.get("chat_capable", True),
            )
            self._profiles[model_id] = profile

    def register_model(self, profile: ModelProfile) -> None:
        with self._lock:
            self._profiles[profile.model_id] = profile

    def sync_from_ollama(self, ollama_api_url: str, *, timeout: float = 5.0) -> int:
        """Register any locally-installed Ollama model not already known
        (HOS-073) — before this, PREDEFINED_MODELS only ever contained the
        12 tags assigned a role in config/models.yaml, so a model the user
        pulled manually (to try it, or to benchmark it) never appeared in
        Model Intelligence at all: no ranking row, no way to select it for
        a benchmark. Best-effort and silent on failure (an unreachable
        Ollama must not break whatever page triggered this): VRAM is
        estimated from Ollama's own reported file size, since no HOS-065C
        benchmark exists yet for a model nobody configured a role for —
        honest until a real benchmark replaces it. Returns the number of
        newly-registered profiles.
        """
        import httpx

        try:
            with httpx.Client(base_url=ollama_api_url.rstrip("/"), timeout=timeout) as client:
                response = client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return 0

        new_count = 0
        with self._lock:
            for entry in payload.get("models") or []:
                tag = str(entry.get("name") or entry.get("model") or "")
                if not tag or tag in self._profiles:
                    continue
                details = entry.get("details") or {}
                try:
                    arch = ModelArchitecture(_infer_architecture(tag))
                except ValueError:
                    arch = ModelArchitecture.OTHER
                is_embedding = (
                    "embed" in tag.lower()
                    or "embed" in str(details.get("family") or "").lower()
                )
                self._profiles[tag] = ModelProfile(
                    model_id=tag,
                    name=tag,
                    architecture=arch,
                    parameters_b=_infer_parameters_b(tag),
                    vram_required_mb=max(1, int(entry.get("size") or 0) // (1024 * 1024)),
                    available_backends=[RuntimeBackend.OLLAMA],
                    tags=["auto-discovered"],
                    chat_capable=not is_embedding,
                )
                new_count += 1
        return new_count

    def get_profile(self, model_id: str) -> ModelProfile | None:
        with self._lock:
            return self._profiles.get(model_id)

    def _score(self, profile: ModelProfile) -> float:
        """The one real ranking score for a profile (HOS-071 Phase B) —
        always analyzer.compute_model_score(), fed this profiler's own real
        performance history for the given model."""
        records = [r for r in self._performance_history if r.model_id == profile.model_id]
        return self._analyzer.compute_model_score(profile, records)

    def list_profiles(self) -> list[ModelProfile]:
        with self._lock:
            return sorted(self._profiles.values(), key=lambda p: -self._score(p))

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

                # tokens_per_second starts at the honest 0.0 (never measured)
                # and is now a running average of real completions — not the
                # random.uniform() BenchmarkScheduler fabricates and never
                # persists (see its docstring). A single slow/fast outlier
                # is smoothed rather than replacing the estimate outright.
                if record.success and record.duration_ms > 0 and record.tokens_used > 0:
                    observed_tps = record.tokens_used / (record.duration_ms / 1000.0)
                    profile.tokens_per_second = (
                        observed_tps if profile.tokens_per_second <= 0
                        else profile.tokens_per_second * 0.7 + observed_tps * 0.3
                    )

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
            return sorted(profiles, key=lambda p: -self._score(p))[:limit]

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
                        "tps": round(p.tokens_per_second, 1),
                        "score": round(self._score(p), 3),
                        "success_rate": round(p.success_rate, 3),
                    }
                    for p in sorted(self._profiles.values(), key=lambda x: -self._score(x))
                ],
            }
