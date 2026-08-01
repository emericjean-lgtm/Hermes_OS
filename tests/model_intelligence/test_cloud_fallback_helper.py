"""Tests for get_cloud_fallback_model() (HOS-066C) — the reusable helper
BaseAgent/TaskDecomposer use to ask "is there a real cloud model to retry
against right now", reusing AdaptiveRouter's exact same gate.

mi_routes._router is monkeypatched (not the public
create_model_intelligence_routes() seeding call) specifically so it is
restored automatically after each test — this module-level singleton is
shared by the whole test session and must not leak between test files.
"""
from __future__ import annotations

from backend.model_intelligence import routes as mi_routes
from backend.model_intelligence.adaptive_router import AdaptiveRouter, CloudGate
from backend.model_intelligence.model_intelligence_models import (
    ModelProfile,
    RuntimeBackend,
)
from backend.model_intelligence.model_predictor import ModelPredictor
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.performance_analyzer import PerformanceAnalyzer


def _local_profile(model_id: str = "qwen3:4b", vram_mb: int = 3000) -> ModelProfile:
    return ModelProfile(model_id=model_id, name=model_id, vram_required_mb=vram_mb,
                        available_backends=[RuntimeBackend.OLLAMA])


def _cloud_profile(model_id: str = "deepseek/deepseek-chat-v3.1:free") -> ModelProfile:
    return ModelProfile(model_id=model_id, name=model_id, vram_required_mb=0,
                        available_backends=[RuntimeBackend.OPENROUTER])


def _router(profiles: list[ModelProfile], *, cloud: CloudGate | None = None) -> AdaptiveRouter:
    profiler = ModelProfiler()
    profiler._profiles.clear()  # noqa: SLF001
    for p in profiles:
        profiler.register_model(p)
    return AdaptiveRouter(
        profiler=profiler, analyzer=PerformanceAnalyzer(), predictor=ModelPredictor(), cloud=cloud,
    )


def _gate(*, authorized: bool = True, has_quota: bool = True) -> CloudGate:
    return CloudGate(authorized=lambda: authorized, has_quota=lambda: has_quota,
                     refresh_catalog=lambda: None)


class TestGetCloudFallbackModel:
    def test_none_when_no_cloud_gate_wired(self, monkeypatch):
        monkeypatch.setattr(mi_routes, "_router", _router([_local_profile(), _cloud_profile()]))
        assert mi_routes.get_cloud_fallback_model("chat") is None

    def test_returns_cloud_model_id_when_authorized_with_quota(self, monkeypatch):
        monkeypatch.setattr(
            mi_routes, "_router",
            _router([_local_profile(), _cloud_profile()], cloud=_gate()),
        )
        assert mi_routes.get_cloud_fallback_model("chat") == "deepseek/deepseek-chat-v3.1:free"

    def test_forces_escalation_even_though_local_looks_viable(self, monkeypatch):
        """The whole point: this is called *after* a local attempt already
        failed for a reason AdaptiveRouter's VRAM-only check can't see
        (Ollama down), so it must not be blocked by "local looks fine"."""
        monkeypatch.setattr(
            mi_routes, "_router",
            _router([_local_profile(vram_mb=100), _cloud_profile()], cloud=_gate()),
        )
        assert mi_routes.get_cloud_fallback_model("chat") is not None

    def test_none_when_not_authorized(self, monkeypatch):
        monkeypatch.setattr(
            mi_routes, "_router",
            _router([_local_profile(), _cloud_profile()], cloud=_gate(authorized=False)),
        )
        assert mi_routes.get_cloud_fallback_model("chat") is None

    def test_none_when_no_quota(self, monkeypatch):
        monkeypatch.setattr(
            mi_routes, "_router",
            _router([_local_profile(), _cloud_profile()], cloud=_gate(has_quota=False)),
        )
        assert mi_routes.get_cloud_fallback_model("chat") is None

    def test_unknown_task_type_string_does_not_crash(self, monkeypatch):
        monkeypatch.setattr(
            mi_routes, "_router",
            _router([_local_profile(), _cloud_profile()], cloud=_gate()),
        )
        assert mi_routes.get_cloud_fallback_model("not-a-real-task-type") == "deepseek/deepseek-chat-v3.1:free"

    def test_none_when_no_cloud_profiles_registered(self, monkeypatch):
        monkeypatch.setattr(
            mi_routes, "_router", _router([_local_profile()], cloud=_gate()),
        )
        assert mi_routes.get_cloud_fallback_model("chat") is None
