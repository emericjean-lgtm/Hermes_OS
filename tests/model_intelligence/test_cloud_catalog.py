"""Tests for CloudModelCatalog (HOS-066C).

No network I/O: every request goes through httpx.MockTransport.
"""
from __future__ import annotations

import httpx
import pytest

from backend.model_intelligence.cloud_catalog import CloudModelCatalog
from backend.model_intelligence.model_intelligence_models import RuntimeBackend
from backend.model_intelligence.model_profiler import ModelProfiler

_MODELS_PAYLOAD = {
    "data": [
        {
            "id": "deepseek/deepseek-chat-v3.1:free",
            "name": "DeepSeek Chat v3.1 (free)",
            "context_length": 65536,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["text"]},
        },
        {
            "id": "meta-llama/llama-3.3-70b:paid",
            "name": "Llama 3.3 70B",
            "context_length": 131072,
            "pricing": {"prompt": "0.0000002", "completion": "0.0000006"},
            "architecture": {"output_modalities": ["text"]},
        },
        {
            "id": "some/vision-model:free",
            "name": "Vision Model (free)",
            "context_length": 32768,
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["image"]},
        },
    ],
}


def _catalog(handler, **kwargs) -> CloudModelCatalog:
    return CloudModelCatalog(
        "test-key", ModelProfiler(), transport=httpx.MockTransport(handler), **kwargs,
    )


class TestRefresh:
    def test_registers_only_free_models(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/models"
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        catalog = _catalog(handler)
        count = catalog.refresh()
        assert count == 2  # the paid entry is excluded
        ids = catalog.registered_model_ids()
        assert "deepseek/deepseek-chat-v3.1:free" in ids
        assert "some/vision-model:free" in ids
        assert "meta-llama/llama-3.3-70b:paid" not in ids

    def test_registered_profiles_carry_zero_local_vram_and_real_context(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        profiler = ModelProfiler()
        catalog = CloudModelCatalog(
            "test-key", profiler, transport=httpx.MockTransport(handler),
        )
        catalog.refresh()
        profile = profiler.get_profile("deepseek/deepseek-chat-v3.1:free")
        assert profile is not None
        assert profile.vram_required_mb == 0
        assert profile.context_window == 65536
        assert RuntimeBackend.OPENROUTER in profile.available_backends
        assert profile.chat_capable is True

    def test_non_text_output_model_is_not_chat_capable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        profiler = ModelProfiler()
        catalog = CloudModelCatalog(
            "test-key", profiler, transport=httpx.MockTransport(handler),
        )
        catalog.refresh()
        profile = profiler.get_profile("some/vision-model:free")
        assert profile is not None
        assert profile.chat_capable is False

    def test_cached_within_ttl(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        catalog = _catalog(handler, catalog_ttl_s=3600.0)
        catalog.refresh()
        catalog.refresh()
        catalog.refresh()
        assert calls["n"] == 1

    def test_force_bypasses_cache(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        catalog = _catalog(handler, catalog_ttl_s=3600.0)
        catalog.refresh()
        catalog.refresh(force=True)
        assert calls["n"] == 2

    def test_fetch_failure_is_best_effort_and_keeps_prior_state(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        catalog = _catalog(handler)
        count = catalog.refresh()
        assert count == 0  # never crashes, just reports nothing registered


class TestHasBudget:
    def test_true_when_remaining_exceeds_reserve(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/key"
            return httpx.Response(200, json={"data": {"limit_remaining": 40}})

        catalog = _catalog(handler, reserve_daily_requests=5)
        assert catalog.has_budget() is True

    def test_false_when_remaining_at_or_below_reserve(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"limit_remaining": 5}})

        catalog = _catalog(handler, reserve_daily_requests=5)
        assert catalog.has_budget() is False

    def test_false_when_quota_unreachable(self):
        """Unknown/unreachable is treated as *no* budget — fail closed
        toward local, never an assumption that quota is fine."""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host", request=request)

        catalog = _catalog(handler)
        assert catalog.has_budget() is False

    def test_false_when_response_shape_is_unparseable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {}})

        catalog = _catalog(handler)
        assert catalog.has_budget() is False

    def test_cached_within_ttl(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"data": {"limit_remaining": 40}})

        catalog = _catalog(handler, quota_ttl_s=3600.0)
        catalog.has_budget()
        catalog.has_budget()
        assert calls["n"] == 1


class TestStatus:
    def test_reports_real_snapshot(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=_MODELS_PAYLOAD)
            return httpx.Response(200, json={"data": {"limit_remaining": 12}})

        catalog = _catalog(handler, reserve_daily_requests=5)
        catalog.refresh()
        catalog.has_budget()
        status = catalog.status()
        assert status["catalog_size"] == 2
        assert status["quota_remaining"] == 12
        assert status["reserve_daily_requests"] == 5
        assert status["catalog_age_s"] is not None
        assert status["quota_checked_age_s"] is not None

    def test_reports_unknowns_before_anything_ran(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_MODELS_PAYLOAD)

        catalog = _catalog(handler)
        status = catalog.status()
        assert status["catalog_size"] == 0
        assert status["quota_remaining"] is None
        assert status["catalog_age_s"] is None
