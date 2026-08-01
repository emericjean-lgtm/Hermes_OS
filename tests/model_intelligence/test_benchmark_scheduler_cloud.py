"""Tests for BenchmarkScheduler's cloud (OpenRouter free-model) benchmark
path (HOS-066C) — dispatch based on the profile's available_backends, real
wall-clock timing + real usage token counts (OpenRouter has no eval_count/
eval_duration the way Ollama does), zero local VRAM.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.model_intelligence.benchmark_scheduler import BenchmarkScheduler
from backend.model_intelligence.model_intelligence_models import (
    ModelProfile,
    RuntimeBackend,
    TaskType,
)
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.performance_analyzer import PerformanceAnalyzer


def _cloud_profile(model_id: str = "deepseek/deepseek-chat-v3.1:free") -> ModelProfile:
    return ModelProfile(
        model_id=model_id, name=model_id, vram_required_mb=0,
        available_backends=[RuntimeBackend.OPENROUTER],
    )


def _local_profile(model_id: str = "qwen3:4b") -> ModelProfile:
    return ModelProfile(
        model_id=model_id, name=model_id, vram_required_mb=3000,
        available_backends=[RuntimeBackend.OLLAMA],
    )


def _scheduler(profiles: list[ModelProfile], *, chat=None, cloud_chat=None) -> BenchmarkScheduler:
    profiler = ModelProfiler()
    profiler._profiles.clear()  # noqa: SLF001 - isolate from config/models.yaml's real roles
    for p in profiles:
        profiler.register_model(p)
    return BenchmarkScheduler(
        profiler=profiler, analyzer=PerformanceAnalyzer(), chat=chat, cloud_chat=cloud_chat,
    )


async def _fake_cloud_chat(*, messages, model, num_ctx):
    await asyncio.sleep(0.01)  # a real (if tiny) wall-clock interval to measure
    return {
        "choices": [{"message": {"content": "a real-shaped cloud completion"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8},
    }


async def _fake_local_chat(*, messages, model, num_ctx):
    return {
        "message": {"content": "local completion"},
        "eval_count": 42, "eval_duration": 500_000_000,
        "prompt_eval_count": 10, "total_duration": 600_000_000,
    }


class TestDispatch:
    def test_cloud_profile_uses_cloud_chat_not_local(self):
        local_calls = {"n": 0}

        async def counting_local(*, messages, model, num_ctx):
            local_calls["n"] += 1
            return await _fake_local_chat(messages=messages, model=model, num_ctx=num_ctx)

        scheduler = _scheduler(
            [_cloud_profile()], chat=counting_local, cloud_chat=_fake_cloud_chat,
        )
        result = scheduler.run_benchmark("deepseek/deepseek-chat-v3.1:free", TaskType.CHAT)
        assert local_calls["n"] == 0
        assert result.quality_score == 1.0
        scheduler.close()

    def test_local_profile_still_uses_ollama_path(self):
        cloud_calls = {"n": 0}

        async def counting_cloud(*, messages, model, num_ctx):
            cloud_calls["n"] += 1
            return await _fake_cloud_chat(messages=messages, model=model, num_ctx=num_ctx)

        scheduler = _scheduler(
            [_local_profile()], chat=_fake_local_chat, cloud_chat=counting_cloud,
        )
        scheduler.run_benchmark("qwen3:4b", TaskType.CHAT)
        assert cloud_calls["n"] == 0
        scheduler.close()


class TestCloudMetrics:
    def test_reports_real_usage_token_counts(self):
        scheduler = _scheduler([_cloud_profile()], cloud_chat=_fake_cloud_chat)
        result = scheduler.run_benchmark("deepseek/deepseek-chat-v3.1:free", TaskType.CHAT)
        # tokens_per_second is computed from real completion_tokens (8) over
        # a real measured wall-clock interval — just assert it's positive,
        # not an exact value, since the interval is a real timing.
        assert result.tokens_per_second > 0
        assert result.latency_ms > 0
        scheduler.close()

    def test_vram_usage_is_zero_for_cloud(self):
        scheduler = _scheduler([_cloud_profile()], cloud_chat=_fake_cloud_chat)
        result = scheduler.run_benchmark("deepseek/deepseek-chat-v3.1:free", TaskType.CHAT)
        assert result.vram_usage_mb == 0
        assert result.ram_usage_mb == 0
        scheduler.close()

    def test_feeds_task_scores_same_as_local_path(self):
        profiler = ModelProfiler()
        profiler._profiles.clear()  # noqa: SLF001
        profile = _cloud_profile()
        profiler.register_model(profile)
        scheduler = BenchmarkScheduler(profiler=profiler, cloud_chat=_fake_cloud_chat)
        scheduler.run_benchmark(profile.model_id, TaskType.CHAT)
        assert profiler.get_profile(profile.model_id).task_scores["chat"] == 1.0
        scheduler.close()

    def test_raises_when_cloud_unreachable(self):
        async def failing_cloud_chat(*, messages, model, num_ctx):
            raise RuntimeError("connection refused")

        scheduler = _scheduler([_cloud_profile()], cloud_chat=failing_cloud_chat)
        with pytest.raises(RuntimeError, match="OpenRouter"):
            scheduler.run_benchmark("deepseek/deepseek-chat-v3.1:free", TaskType.CHAT)
        scheduler.close()

    def test_default_cloud_chat_raises_without_api_key(self, monkeypatch):
        """No injected cloud_chat and no OPENROUTER_API_KEY configured —
        must raise plainly, never silently produce fabricated numbers."""
        from backend.core.config import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        scheduler = _scheduler([_cloud_profile()])
        try:
            with pytest.raises(RuntimeError):
                scheduler.run_benchmark("deepseek/deepseek-chat-v3.1:free", TaskType.CHAT)
        finally:
            scheduler.close()
            get_settings.cache_clear()
