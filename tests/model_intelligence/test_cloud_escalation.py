"""Tests for AdaptiveRouter's cloud (OpenRouter free-model) escalation gate
(HOS-066C) — local-first by construction, cloud only when genuinely needed
and authorized, automatic fallback to local otherwise.
"""
from __future__ import annotations

from backend.model_intelligence.adaptive_router import AdaptiveRouter, CloudGate
from backend.model_intelligence.model_intelligence_models import (
    ModelProfile,
    RuntimeBackend,
    TaskContext,
    TaskType,
)
from backend.model_intelligence.model_predictor import ModelPredictor
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.performance_analyzer import PerformanceAnalyzer


def _local_profile(model_id: str = "qwen3:4b", vram_mb: int = 3000) -> ModelProfile:
    return ModelProfile(
        model_id=model_id, name=model_id, vram_required_mb=vram_mb,
        available_backends=[RuntimeBackend.OLLAMA],
    )


def _cloud_profile(model_id: str = "deepseek/deepseek-chat-v3.1:free") -> ModelProfile:
    return ModelProfile(
        model_id=model_id, name=model_id, vram_required_mb=0,
        available_backends=[RuntimeBackend.OPENROUTER],
    )


def _router(profiles: list[ModelProfile], *, cloud: CloudGate | None = None) -> AdaptiveRouter:
    profiler = ModelProfiler()
    # ModelProfiler() always seeds itself from config/models.yaml's real
    # roles (PREDEFINED_MODELS) — clearing them isolates these tests from
    # this deployment's actual role catalogue, which is irrelevant to (and
    # would make brittle) testing the escalation *gate* logic itself.
    profiler._profiles.clear()  # noqa: SLF001
    for p in profiles:
        profiler.register_model(p)
    router = AdaptiveRouter(
        profiler=profiler, analyzer=PerformanceAnalyzer(), predictor=ModelPredictor(),
        cloud=cloud,
    )
    return router


def _gate(*, authorized: bool = True, has_quota: bool = True, refreshed: list | None = None) -> CloudGate:
    calls = refreshed if refreshed is not None else []
    return CloudGate(
        authorized=lambda: authorized,
        has_quota=lambda: has_quota,
        refresh_catalog=lambda: calls.append(True),
    )


class TestNoCloudConfigured:
    def test_recommend_is_unchanged_when_no_gate_is_wired(self):
        """The default (cloud=None) must behave exactly as before this
        feature existed — no cloud profile is ever picked, regardless of
        local viability."""
        router = _router([_local_profile(), _cloud_profile()])
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA
        assert decision.model_id == "qwen3:4b"


class TestLocalFirst:
    def test_local_model_wins_even_when_cloud_is_authorized(self):
        """A viable local model exists and the task did not opt in — cloud
        must not even be considered."""
        router = _router(
            [_local_profile(), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True),
        )
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA

    def test_cloud_used_when_no_local_model_is_viable(self):
        """No local profile fits the VRAM budget — the one honest case
        where cloud may be used without an explicit opt-in."""
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True),
        )
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OPENROUTER
        assert "no local model was viable" in decision.reason

    def test_cloud_used_when_task_explicitly_opts_in(self):
        router = _router(
            [_local_profile(), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True),
        )
        decision = router.recommend(
            TaskContext(max_vram_mb=8192, cloud_escalation_allowed=True)
        )
        assert decision.runtime == RuntimeBackend.OPENROUTER
        assert "task opted in" in decision.reason

    def test_allow_cloud_false_forces_local_even_when_opted_in(self):
        """The escape hatch RealTaskExecutor uses to compute a local
        fallback after a cloud failure — must never recommend cloud."""
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True),
        )
        decision = router.recommend(
            TaskContext(max_vram_mb=8192, cloud_escalation_allowed=True),
            allow_cloud=False,
        )
        assert decision.runtime == RuntimeBackend.OLLAMA


class TestAutomaticFallback:
    def test_falls_back_to_local_when_not_authorized(self):
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=False, has_quota=True),
        )
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA
        # No local model is *viable* either -> the "lightest known" floor.
        assert decision.model_id == "qwen3:4b"

    def test_falls_back_to_local_when_quota_exhausted(self):
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=False),
        )
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA

    def test_falls_back_to_local_when_gate_raises(self):
        """A broken gate must degrade to "cloud unavailable", never crash
        recommend()."""
        def _boom() -> bool:
            raise RuntimeError("Aegis config missing")

        cloud = CloudGate(authorized=_boom, has_quota=lambda: True,
                          refresh_catalog=lambda: None)
        router = _router([_local_profile(vram_mb=50_000), _cloud_profile()], cloud=cloud)
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA

    def test_falls_back_to_local_when_no_cloud_profiles_registered(self):
        router = _router(
            [_local_profile(vram_mb=50_000)],  # no cloud profile at all
            cloud=_gate(authorized=True, has_quota=True),
        )
        decision = router.recommend(TaskContext(max_vram_mb=8192))
        assert decision.runtime == RuntimeBackend.OLLAMA


class TestCatalogRefresh:
    def test_refresh_catalog_is_called_before_ranking_cloud_candidates(self):
        calls: list[bool] = []
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True, refreshed=calls),
        )
        router.recommend(TaskContext(max_vram_mb=8192))
        assert calls == [True]

    def test_not_called_when_no_local_fallback_needed(self):
        """Cloud is never even attempted when a local model is viable —
        refresh_catalog must not fire either."""
        calls: list[bool] = []
        router = _router(
            [_local_profile(), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True, refreshed=calls),
        )
        router.recommend(TaskContext(max_vram_mb=8192))
        assert calls == []


class TestFallbackDecisionNeverPicksCloud:
    def test_fallback_decision_ignores_zero_vram_cloud_profiles(self):
        """Regression guard: cloud profiles carry vram_required_mb=0, which
        would win min() outright and silently bypass every auth/quota check
        if _fallback_decision ever considered them."""
        router = _router([_cloud_profile(), _local_profile(vram_mb=50_000)])
        decision = router._fallback_decision(TaskContext(max_vram_mb=8192))  # noqa: SLF001
        assert decision.runtime == RuntimeBackend.OLLAMA
        assert decision.model_id == "qwen3:4b"


class TestRecommendForText:
    def test_allow_cloud_passthrough(self):
        router = _router(
            [_local_profile(vram_mb=50_000), _cloud_profile()],
            cloud=_gate(authorized=True, has_quota=True),
        )
        local_only = router.recommend_for_text("write a function", allow_cloud=False)
        assert local_only.runtime == RuntimeBackend.OLLAMA
        cloud_ok = router.recommend_for_text("write a function", allow_cloud=True)
        assert cloud_ok.runtime == RuntimeBackend.OPENROUTER
