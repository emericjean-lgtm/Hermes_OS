"""Tests for HOS-073 — "not all models appear" fix in the Models Center.

Two real, compounding bugs found from a user bug report:

* GET /models/ranking defaulted to limit=5 (both the route's own Query
  default and handle_get_ranking's own default), and the Cockpit's
  ranking table / benchmark model-select called it with no explicit
  limit — so only the top 5 of every registered model ever appeared,
  regardless of how many were really available (config/models.yaml alone
  defines 12 roles).
* ModelProfiler only ever knew about the 12 models assigned a role in
  config/models.yaml (PREDEFINED_MODELS) — a model the user pulled
  manually to try or benchmark never appeared at all, with no way to add
  it short of editing that file and inventing a role for it.

Fully hermetic: a fake httpx transport stands in for Ollama's /api/tags,
no real Ollama needed.
"""
from __future__ import annotations

import httpx
import pytest

from backend.model_intelligence.model_intelligence_models import RuntimeBackend
from backend.model_intelligence.model_profiler import ModelProfiler

_RealClient = httpx.Client  # captured before any monkeypatching


def _mock_ollama_client(handler):
    """Real httpx.Client, transport swapped for a mock — avoids recursion
    from patching httpx.Client itself while still calling it inside."""
    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _RealClient(transport=httpx.MockTransport(handler), **kwargs)
    return factory


class TestSyncFromOllama:
    def test_registers_a_model_not_in_any_role(self, monkeypatch):
        profiler = ModelProfiler()
        assert profiler.get_profile("prism-ml/ternary-bonsai-27b:q2") is None

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": [
                {"name": "prism-ml/ternary-bonsai-27b:q2",
                 "size": 10_000_000_000,
                 "details": {"family": "bonsai", "parameter_size": "27B"}},
            ]})

        monkeypatch.setattr(httpx, "Client", _mock_ollama_client(handler))
        new_count = profiler.sync_from_ollama("http://fake-ollama")

        assert new_count == 1
        profile = profiler.get_profile("prism-ml/ternary-bonsai-27b:q2")
        assert profile is not None
        assert profile.parameters_b == 27.0
        assert profile.vram_required_mb == 10_000_000_000 // (1024 * 1024)
        assert profile.chat_capable is True
        assert RuntimeBackend.OLLAMA in profile.available_backends
        assert profile.tags == ["auto-discovered"]

    def test_does_not_overwrite_an_already_known_model(self, monkeypatch):
        # Le tag vient de la configuration : « qwen3.5:2b » etait le role
        # swift en juillet et n'existe plus depuis le renommage.
        from backend.core.config import load_models_config

        connu = load_models_config()["roles"]["swift"]["model"]
        profiler = ModelProfiler()
        existing = profiler.get_profile(connu)
        assert existing is not None  # from config/models.yaml's real roles

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": [
                {"name": connu, "size": 1, "details": {}},
            ]})

        monkeypatch.setattr(httpx, "Client", _mock_ollama_client(handler))
        new_count = profiler.sync_from_ollama("http://fake-ollama")

        assert new_count == 0
        # Still the real, curated profile — not overwritten by the
        # auto-discovered fallback's honest-but-cruder defaults.
        assert profiler.get_profile(connu) is existing

    def test_embedding_model_is_marked_not_chat_capable(self, monkeypatch):
        profiler = ModelProfiler()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": [
                {"name": "mxbai-embed-large", "size": 1,
                 "details": {"family": "bert"}},
            ]})

        monkeypatch.setattr(httpx, "Client", _mock_ollama_client(handler))
        profiler.sync_from_ollama("http://fake-ollama")
        profile = profiler.get_profile("mxbai-embed-large")
        assert profile is not None
        assert profile.chat_capable is False

    def test_unreachable_ollama_returns_zero_not_fabricated(self, monkeypatch):
        profiler = ModelProfiler()

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        monkeypatch.setattr(httpx, "Client", _mock_ollama_client(handler))
        assert profiler.sync_from_ollama("http://fake-ollama") == 0

    def test_new_model_shows_up_in_ranking(self, monkeypatch):
        """The actual bug: a newly-registered model must appear in the
        same listing the Cockpit's ranking table and benchmark
        model-select both read from."""
        profiler = ModelProfiler()
        before = {p.model_id for p in profiler.list_profiles()}
        assert "custom-model:latest" not in before

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": [
                {"name": "custom-model:latest", "size": 5_000_000_000, "details": {}},
            ]})

        monkeypatch.setattr(httpx, "Client", _mock_ollama_client(handler))
        profiler.sync_from_ollama("http://fake-ollama")
        after = {p.model_id for p in profiler.list_profiles()}
        assert "custom-model:latest" in after


class TestDuplicateTagFix:
    """User-reported React console error: "Encountered two children with
    the same key, `standard`." — config/models.yaml's "standard" role has
    tier "standard" too, so tags=[role_name, tier] produced the literal
    string twice, colliding as a React key in the Cockpit's tags list."""

    def test_role_whose_tier_equals_its_own_name_is_not_duplicated(self):
        # Le tag du role `standard` vient de la configuration : ce test
        # portait sur « qwen3.5:9b », vrai en juillet et disparu depuis.
        # Ce qui est verifie est la deduplication, pas l'identite du modele.
        from backend.core.config import load_models_config
        from backend.model_intelligence.model_profiler import PREDEFINED_MODELS

        tag = load_models_config()["roles"]["standard"]["model"]
        standard = PREDEFINED_MODELS.get(tag)

        assert standard is not None
        assert standard["tags"] == ["standard"]

    def test_no_registered_profile_has_duplicate_tags(self):
        profiler = ModelProfiler()
        for profile in profiler.list_profiles():
            assert len(profile.tags) == len(set(profile.tags)), (
                f"{profile.model_id} has duplicate tags: {profile.tags}"
            )


class TestRankingLimitFix:
    def test_route_default_limit_covers_every_known_role_model(self):
        """HOS-073: config/models.yaml alone defines 12 roles — the route's
        own default must not silently truncate below that."""
        import backend.model_intelligence.routes as mi_routes

        result = mi_routes.handle_get_ranking()
        # 12 role-based models is the real, current floor — this must not
        # regress back to a default that hides most of them.
        assert len(result["models"]) >= 12

    def test_handle_get_ranking_default_is_not_five(self):
        import inspect

        import backend.model_intelligence.routes as mi_routes

        sig = inspect.signature(mi_routes.handle_get_ranking)
        assert sig.parameters["limit"].default > 5
