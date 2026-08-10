from __future__ import annotations

import pytest

from backend.core.router import ModelRouter, UnknownTaskTypeError


def test_prefers_already_loaded_model(models_config):
    router = ModelRouter(models_config)
    # the orchestrator model is a lower-priority candidate for
    # "conversation" than standard/swift — proves "already loaded" wins
    # over priority order, not just that the top candidate got picked.
    orchestrator_model = models_config["roles"]["orchestrator"]["model"]
    decision = router.select_model("conversation", loaded_models=[orchestrator_model])
    assert decision.model == orchestrator_model
    assert "already loaded" in decision.reason


def test_default_priority_without_vram_info(models_config):
    router = ModelRouter(models_config)
    decision = router.select_model("conversation")
    assert decision.role == "standard"
    assert "no VRAM constraint" in decision.reason


def test_respects_vram_budget(models_config):
    router = ModelRouter(models_config)
    # code: 17GB, code_agentic: 14GB (HOS-079) — a 5GB budget fits neither.
    decision = router.select_model("code_generation", available_vram_gb=5)
    assert decision.reason.startswith("no candidate fits")
    # Falls back to the smallest of the two candidates.
    assert decision.role == "code_agentic"


def test_picks_candidate_that_fits(models_config):
    router = ModelRouter(models_config)
    # Between the two candidates (code_agentic 14GB, code 17GB): only
    # code_agentic fits.
    decision = router.select_model("code_generation", available_vram_gb=15)
    assert decision.role == "code_agentic"
    assert "fits available VRAM" in decision.reason


def test_unknown_task_type_raises(models_config):
    router = ModelRouter(models_config)
    with pytest.raises(UnknownTaskTypeError):
        router.select_model("not_a_real_task_type")


def test_model_for_role_resolves_directly(models_config):
    router = ModelRouter(models_config)
    assert router.model_for_role("security") == models_config["roles"]["security"]["model"]
