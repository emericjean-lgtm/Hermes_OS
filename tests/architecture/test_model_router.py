"""Tests for ModelRouter (backend/core/router.py), focused on num_ctx
(HOS-065C) — no dedicated test file existed for this module before.

Every RoutingDecision used to report num_ctx=8192 unconditionally: the
constructor default was never overridden, so every chat_events() call this
router informed used one global context window regardless of which model
actually answered. See config/models.yaml's roles.*.num_ctx and CHANGELOG.
"""

from __future__ import annotations

from backend.core.config import load_models_config
from backend.core.router import ModelRouter, RoutingDecision, UnknownTaskTypeError

import pytest


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(load_models_config())


class TestNumCtx:
    def test_select_model_reports_the_role_specific_num_ctx(self, router):
        decision = router.select_model("planning")  # -> orchestrator role
        assert decision.role == "orchestrator"
        assert decision.num_ctx == 16384

    def test_different_roles_report_different_num_ctx(self, router):
        """Every role used to report the same 8192 regardless of which
        model was chosen — confirm two roles with genuinely different
        configured values actually differ."""
        swift_decision = router.select_model("classification")  # -> swift, no VRAM constraint
        standard_decision = router.select_model("conversation")  # -> standard, first candidate
        assert swift_decision.role == "swift"
        assert standard_decision.role == "standard"
        assert swift_decision.num_ctx == 16384
        assert standard_decision.num_ctx == 32768

    def test_embedding_role_stays_within_its_real_model_limit(self, router):
        """nomic-embed-text's real max context is 2048 (`ollama show
        nomic-embed-text`) — the old global default (8192) exceeded it for
        every embedding call this deployment ever made."""
        decision = router.select_model("embedding")
        assert decision.role == "embedding"
        assert decision.num_ctx == 2048

    def test_reasoning_escalation_was_not_raised_like_the_other_roles(self, router):
        """deepseek-r1:32b measured 95.8s latency / 6.6 tok/s / 9.5GB RAM
        offload at just 16384 in the real HOS-065C benchmark — the one role
        this pass deliberately left at the pre-HOS-065C default rather than
        increasing it, because raising it would make an already-marginal
        situation worse, not better."""
        role = router._roles["reasoning_escalation"]  # noqa: SLF001
        assert role.get("num_ctx", 8192) == 8192


class TestForcedRole:
    """HOS-075 — manual model choice / reasoning-effort presets from the
    Assistant: the role *is* the decision, bypassing candidate ranking."""

    def test_decision_for_role_returns_the_roles_real_config(self, router):
        decision = router.decision_for_role("orchestrator", "conversation")
        assert decision.role == "orchestrator"
        assert decision.model == router.model_for_role("orchestrator")
        assert decision.num_ctx == 16384

    def test_thinking_none_keeps_the_task_types_own_policy(self, router):
        auto = router.select_model("planning")
        forced = router.decision_for_role("orchestrator", "planning", thinking=None)
        assert forced.thinking == auto.thinking

    def test_thinking_true_overrides_a_task_type_that_would_be_false(self, router):
        auto = router.select_model("conversation")
        assert auto.thinking is False  # conversation doesn't normally reason
        forced = router.decision_for_role("standard", "conversation", thinking=True)
        assert forced.thinking is True

    def test_thinking_false_overrides_a_task_type_that_would_be_true(self, router):
        auto = router.select_model("planning")
        assert auto.thinking is True  # planning normally reasons
        forced = router.decision_for_role("orchestrator", "planning", thinking=False)
        assert forced.thinking is False

    def test_unknown_role_raises_key_error_not_a_silent_fallback(self, router):
        with pytest.raises(KeyError):
            router.decision_for_role("not-a-real-role", "conversation")

    def test_known_roles_lists_every_configured_role(self, router):
        roles = router.known_roles()
        assert "swift" in roles
        assert "reasoning_escalation" in roles
        assert roles == sorted(roles)


class TestNumCtxDefaults:
    def test_num_ctx_defaults_to_8192_for_a_role_missing_the_field(self):
        """A role that predates this pass (or a test config without
        num_ctx) must not crash — it degrades to the old global default,
        not an exception."""
        router = ModelRouter({
            "roles": {"bare": {"model": "some-model", "tier": "standard", "vram_gb": 1}},
            "routing": {"chat": ["bare"]},
        })
        decision = router.select_model("chat")
        assert decision.num_ctx == 8192


class TestSelectModel:
    """Minimal sanity coverage for select_model() itself, since no test
    file previously existed for this module at all."""

    def test_unknown_task_type_raises(self, router):
        with pytest.raises(UnknownTaskTypeError):
            router.select_model("not_a_real_task_type")

    def test_prefers_already_loaded_model(self, router):
        candidates = router._routing["conversation"]  # noqa: SLF001
        loaded_tag = router._roles[candidates[-1]]["model"]  # noqa: SLF001
        decision = router.select_model("conversation", loaded_models=[loaded_tag])
        assert decision.model == loaded_tag
        assert "already loaded" in decision.reason

    def test_downgrades_when_nothing_fits_available_vram(self, router):
        decision = router.select_model("code_generation", available_vram_gb=0.01)
        assert "downgraded" in decision.reason

    def test_model_for_role_bypasses_task_type_routing(self, router):
        assert router.model_for_role("security") == router._roles["security"]["model"]  # noqa: SLF001

    def test_returns_a_real_routing_decision(self, router):
        decision = router.select_model("code_generation", available_vram_gb=100)
        assert isinstance(decision, RoutingDecision)
        assert decision.model  # a real, non-empty tag from config/models.yaml
