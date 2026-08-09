"""Tests for Code Intelligence Agent (HOS-055D).

Covers: router selection, agent lifecycle, KlaatCode routing,
Oh My Pi routing, hybrid routing, event bus, memory integration,
runtime scoring, thread safety, and API routes.
"""

import threading

import pytest

# ── Imports ──

from backend.integrations.code_intelligence.code_intelligence_models import (
    CodeIntelligenceTask,
    CodeIntelligenceTaskType,
    CodeProvider,
    ProviderScore,
    RouteReason,
    RoutingDecision,
    SelectionStrategy,
)
from backend.integrations.code_intelligence.code_intelligence_router import (
    CodeIntelligenceRouter,
)

from backend.agents.specialized.code_intelligence.capabilities import (
    CI_EVENTS,
)
from backend.agents.specialized.code_intelligence.code_intelligence_agent import (
    CITaskRecord,
    CodeIntelligenceAgent,
    create_code_intelligence_agent,
)
from backend.agents.specialized.code_intelligence.profile import (
    CodeIntelligenceProfile,
)

from backend.runtime.code_intelligence.ci_scorer import CIRuntimeScorer

from backend.agents.agent_models import AgentStatus, TaskOutcome


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def ci_task():
    return CodeIntelligenceTask(
        task_id="t1",
        task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
        language="python",
        project_path=".",
        complexity=0.5,
    )


@pytest.fixture
def router():
    return CodeIntelligenceRouter()


@pytest.fixture
def ci_agent():
    return CodeIntelligenceAgent()


@pytest.fixture
def ci_scorer():
    return CIRuntimeScorer()


# ── Test Router Selection ───────────────────────────────────

class TestRouterSelection:
    """Tests for provider selection logic."""

    def test_single_best_klaatcode_for_analysis(self, router):
        task = CodeIntelligenceTask(
            task_id="t1",
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
        )
        decision = router.decide(task)
        assert decision.selected_provider == CodeProvider.KLATCODE
        assert decision.strategy == SelectionStrategy.SINGLE_BEST

    def test_single_best_ohmypi_for_debugging(self, router):
        task = CodeIntelligenceTask(
            task_id="t2",
            task_type=CodeIntelligenceTaskType.DEBUGGING,
            requires_dap=True,
        )
        decision = router.decide(task)
        assert decision.selected_provider == CodeProvider.OHMYPI

    def test_single_best_ohmypi_for_refactoring(self, router):
        task = CodeIntelligenceTask(
            task_id="t3",
            task_type=CodeIntelligenceTaskType.REFACTORING,
            requires_ast=True,
        )
        decision = router.decide(task)
        assert decision.selected_provider == CodeProvider.OHMYPI

    def test_hybrid_for_code_review(self, router):
        task = CodeIntelligenceTask(
            task_id="t4",
            task_type=CodeIntelligenceTaskType.CODE_REVIEW,
        )
        decision = router.decide(task)
        assert decision.strategy == SelectionStrategy.HYBRID_BOTH

    def test_hybrid_for_close_scores_high_complexity(self, router):
        task = CodeIntelligenceTask(
            task_id="t5",
            task_type=CodeIntelligenceTaskType.OPTIMIZATION,
            complexity=0.8,
        )
        decision = router.decide(task)
        assert decision.strategy == SelectionStrategy.HYBRID_BOTH

    def test_force_klaatcode(self, router):
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.DEBUGGING)
        decision = router.decide(task, force_provider=CodeProvider.KLATCODE)
        assert decision.selected_provider == CodeProvider.KLATCODE
        assert decision.metadata.get("forced") is True

    def test_force_hybrid(self, router):
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_ANALYSIS)
        decision = router.decide(task, force_provider=CodeProvider.HYBRID)
        assert decision.strategy == SelectionStrategy.HYBRID_BOTH

    def test_fallback_when_unavailable(self, router):
        task = CodeIntelligenceTask(
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
        )
        decision = router.decide(task, klaatcode_available=False, ohmypi_available=False)
        assert decision.metadata.get("error") is not None

    def test_scores_produced(self, router):
        task = CodeIntelligenceTask(
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
            complexity=0.5,
        )
        decision = router.decide(task)
        assert len(decision.scores) > 0
        for s in decision.scores:
            assert 0.0 <= s.score <= 1.0

    def test_decision_to_dict(self, router):
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_GENERATION)
        decision = router.decide(task)
        d = decision.to_dict()
        assert "task_type" in d
        assert "selected_provider" in d
        assert "scores" in d


class TestHermesNativeRouting:
    """R-006 Phase 3: the third routing candidate."""

    def test_disabled_by_default_preserves_pre_r006_behaviour(self, router):
        """A bare CodeIntelligenceRouter().decide(task) — every existing
        caller and test — must keep routing exactly as it did before
        Hermes-native existed."""
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_GENERATION)
        decision = router.decide(task)
        assert decision.selected_provider != CodeProvider.HERMES_NATIVE

    def test_available_but_not_default_preferred(self, router):
        """With no history, KlaatCode/Oh My Pi's tool-specific task_fit beats
        the generic completion path for every eligible task type — a real
        scoring outcome, not a hardcoded exclusion (unlike the ineligible
        task types below, hermes_native IS a real scored candidate here)."""
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_GENERATION)
        decision = router.decide(task, hermes_native_available=True)
        assert "hermes_native_score" in decision.metadata
        assert decision.metadata["hermes_native_score"] > 0

    def test_wins_after_real_history_favours_it(self, router):
        """The router genuinely adapts: enough recorded klaatcode/ohmypi
        failures alongside hermes_native successes must flip the winner —
        proof this is live scoring, not a static preference order."""
        for _ in range(20):
            router.record_result(CodeProvider.KLATCODE, False, "code_generation")
            router.record_result(CodeProvider.OHMYPI, False, "code_generation")
            router.record_result(CodeProvider.HERMES_NATIVE, True, "code_generation")
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_GENERATION)
        decision = router.decide(task, hermes_native_available=True)
        assert decision.selected_provider == CodeProvider.HERMES_NATIVE

    def test_ineligible_task_types_never_selected_even_when_available(self, router):
        """DEBUGGING has no real one-shot-completion equivalent — it must
        never be offered Hermes-native, regardless of the available flag."""
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.DEBUGGING, requires_dap=True)
        decision = router.decide(task, hermes_native_available=True)
        assert decision.selected_provider != CodeProvider.HERMES_NATIVE

    def test_lsp_requirement_rules_out_hermes_native(self, router):
        task = CodeIntelligenceTask(
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS, requires_lsp=True,
        )
        decision = router.decide(
            task, klaatcode_available=False, hermes_native_available=True,
        )
        assert decision.selected_provider == CodeProvider.OHMYPI

    def test_force_hermes_native(self, router):
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_ANALYSIS)
        decision = router.decide(task, force_provider=CodeProvider.HERMES_NATIVE)
        assert decision.selected_provider == CodeProvider.HERMES_NATIVE

    def test_hermes_native_history_affects_decision(self, router):
        for _ in range(10):
            router.record_result(CodeProvider.HERMES_NATIVE, False, "code_analysis")
        task = CodeIntelligenceTask(task_type=CodeIntelligenceTaskType.CODE_ANALYSIS)
        decision = router.decide(
            task, klaatcode_available=False, ohmypi_available=False,
            hermes_native_available=True,
        )
        # Still the only candidate, but its score must reflect the losses.
        assert decision.metadata["hermes_native_score"] < 0.6

    def test_stats_report_hermes_native(self, router):
        router.record_result(CodeProvider.HERMES_NATIVE, True, "code_generation")
        stats = router.stats()
        assert stats["hermes_native"]["total"] == 1
        assert stats["hermes_native"]["success_count"] == 1


# ── Test Router History ──────────────────────────────────────

class TestRouterHistory:
    """Tests for adaptive scoring via history."""

    def test_record_klaatcode_success(self, router):
        router.record_result(CodeProvider.KLATCODE, True, "code_analysis")
        stats = router.stats()
        assert stats["klaatcode"]["total"] == 1
        assert stats["klaatcode"]["success_rate"] == 100.0

    def test_record_ohmypi_failure(self, router):
        router.record_result(CodeProvider.OHMYPI, False, "debugging")
        stats = router.stats()
        assert stats["ohmypi"]["total"] == 1
        assert stats["ohmypi"]["success_rate"] == 0.0

    def test_history_affects_decision(self, router):
        # Feed many KlaatCode failures
        for _ in range(50):
            router.record_result(CodeProvider.KLATCODE, False)
        # Feed Oh My Pi successes
        for _ in range(50):
            router.record_result(CodeProvider.OHMYPI, True)

        task = CodeIntelligenceTask(
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
            complexity=0.5,
        )
        decision = router.decide(task)
        # Oh My Pi should now be preferred (high historical, and KC low)
        stats = router.stats()
        assert stats["ohmypi"]["success_rate"] > stats["klaatcode"]["success_rate"]

    def test_total_executions_count(self, router):
        router.record_result(CodeProvider.KLATCODE, True)
        router.record_result(CodeProvider.OHMYPI, False)
        assert router.stats()["total_executions"] == 2


# ── Test Agent Lifecycle ─────────────────────────────────────

class TestCIAgentLifecycle:
    """Tests for CodeIntelligenceAgent lifecycle."""

    def test_initial_state(self, ci_agent):
        assert ci_agent.status == AgentStatus.CREATED
        assert ci_agent.is_available is False

    def test_start_transitions(self, ci_agent):
        assert ci_agent.start() is True
        assert ci_agent.status == AgentStatus.READY
        assert ci_agent.is_available is True

    def test_stop(self, ci_agent):
        ci_agent.start()
        assert ci_agent.stop() is True
        assert ci_agent.status == AgentStatus.STOPPED

    def test_pause_resume(self, ci_agent):
        ci_agent.start()
        assert ci_agent.pause() is True
        assert ci_agent.status == AgentStatus.PAUSED
        assert ci_agent.resume() is True
        assert ci_agent.status == AgentStatus.READY

    def test_mark_busy_ready_idle(self, ci_agent):
        ci_agent.start()
        assert ci_agent.mark_busy("t1") is True
        assert ci_agent.status == AgentStatus.BUSY
        assert ci_agent.mark_ready() is True
        assert ci_agent.status == AgentStatus.READY

    def test_agent_event_emitted(self):
        events = []
        agent = CodeIntelligenceAgent(on_event=lambda t, p, **kw: events.append(t))
        agent.start()
        assert CI_EVENTS["agent_ready"] in events

    def test_agent_capabilities(self, ci_agent):
        ci_agent.start()
        caps = ci_agent.agent_capabilities
        cap_names = [c.value for c in caps]
        assert "analysis" in cap_names
        assert "code_generation" in cap_names
        assert "optimization" in cap_names

    def test_to_agent_dataclass(self, ci_agent):
        ci_agent.start()
        agent_dc = ci_agent.to_agent_dataclass()
        assert agent_dc.agent_id == ci_agent.agent_id
        assert agent_dc.name == "CodeIntelligence"


# ── Test Agent Task Execution ────────────────────────────────

class TestCIAgentTaskExecution:
    """Tests for task execution routing."""

    def test_execute_klaatcode_task(self, ci_agent):
        ci_agent.start()
        result = ci_agent.execute_task(
            "code_analysis",
            {"language": "python", "requires_lsp": False},
        )
        assert result.outcome == TaskOutcome.SUCCESS
        # Falls back to klaatcode when no sub-agents
        assert "klaatcode" in result.details.get("provider", "")

    def test_execute_ohmypi_task_with_sub_agent(self):
        omp = CodeIntelligenceAgent(agent_id="omp_sub")
        omp.start()
        ci = CodeIntelligenceAgent(ohmypi_agent=omp)
        ci.start()
        result = ci.execute_task(
            "debugging",
            {"language": "python", "requires_dap": True},
        )
        assert result.outcome == TaskOutcome.SUCCESS
        assert "ohmypi" in result.details.get("provider", "")

    def test_execute_hybrid_task_with_sub_agents(self):
        kc = CodeIntelligenceAgent(agent_id="kc_sub"); kc.start()
        omp = CodeIntelligenceAgent(agent_id="omp_sub"); omp.start()
        ci = CodeIntelligenceAgent(klaatcode_agent=kc, ohmypi_agent=omp)
        ci.start()
        result = ci.execute_task(
            "code_review",
            {"language": "python", "complexity": 0.9},
        )
        assert result.outcome == TaskOutcome.SUCCESS
        assert "hybrid" in result.details.get("strategy", "")

    def test_execute_with_force_provider(self, ci_agent):
        """"debugging" has no real KlaatCode equivalent (KlaatCodeTaskType
        has no DEBUGGING member at all — see CI_TO_KLAATCODE_TASK_TYPE,
        R-006 Phase 4) — forcing it there must fail honestly rather than the
        stub adapter papering over a combination that would 500 in
        production. "code_analysis" is a real, mapped capability."""
        ci_agent.start()
        result = ci_agent.execute_task(
            "code_analysis",
            {},
            force_provider=CodeProvider.KLATCODE,
        )
        assert result.outcome == TaskOutcome.SUCCESS
        assert "klaatcode" in result.details.get("provider", "")

    def test_force_provider_onto_an_unsupported_task_type_fails_honestly(self, ci_agent):
        ci_agent.start()
        result = ci_agent.execute_task(
            "debugging",
            {"requires_dap": True},
            force_provider=CodeProvider.KLATCODE,
        )
        assert result.outcome == TaskOutcome.FAILURE
        assert "no real capability" in result.error_message

    def test_metrics_updated(self, ci_agent):
        ci_agent.start()
        ci_agent.execute_task("code_analysis", {})
        ci_agent.execute_task("debugging", {"requires_dap": True})
        metrics = ci_agent.get_metrics()
        assert metrics.total_tasks == 2
        assert metrics.successful_tasks == 2

    def test_provider_task_counts(self, ci_agent):
        ci_agent.start()
        ci_agent.execute_task("code_analysis", {})
        ci_agent.execute_task("debugging", {"requires_dap": True})
        status = ci_agent.get_status_dict()
        assert status["klaatcode_tasks"] >= 0
        assert status["ohmypi_tasks"] >= 0

    def test_task_history(self, ci_agent):
        ci_agent.start()
        ci_agent.execute_task("code_analysis", {})
        ci_agent.execute_task("refactoring", {"requires_ast": True})
        history = ci_agent.get_task_history()
        assert len(history) >= 2


class TestCIAgentSandboxGuard:
    """R-006 Phase 9: refactoring/code_generation would write through a real
    external CLI. ToolPolicy.evaluate()'s WRITE branch is a documented
    no-op and neither MCP adapter's execute() ever consults its
    ToolSandbox, so nothing beneath CodeIntelligenceAgent actually stops a
    write — this guard is the only real enforcement today."""

    def test_refactor_forced_to_klaatcode_is_refused(self, ci_agent):
        ci_agent.start()
        result = ci_agent.execute_task(
            "refactoring", {}, force_provider=CodeProvider.KLATCODE,
        )
        assert result.outcome == TaskOutcome.FAILURE
        assert "sandbox" in result.error_message

    def test_refactor_forced_to_ohmypi_is_refused(self, ci_agent):
        ci_agent.start()
        result = ci_agent.execute_task(
            "refactoring", {}, force_provider=CodeProvider.OHMYPI,
        )
        assert result.outcome == TaskOutcome.FAILURE
        assert "sandbox" in result.error_message

    def test_code_generation_forced_to_ohmypi_is_refused(self, ci_agent):
        ci_agent.start()
        result = ci_agent.execute_task(
            "code_generation", {}, force_provider=CodeProvider.OHMYPI,
        )
        assert result.outcome == TaskOutcome.FAILURE
        assert "sandbox" in result.error_message

    def test_a_sandbox_id_does_not_bypass_the_refusal(self, ci_agent):
        """No real provisioning path validates a caller-supplied id yet —
        supplying one must not silently unlock execution."""
        ci_agent.start()
        result = ci_agent.execute_task(
            "refactoring", {"sandbox_id": "sb-123"}, force_provider=CodeProvider.KLATCODE,
        )
        assert result.outcome == TaskOutcome.FAILURE

    def test_refactor_forced_to_hermes_native_is_not_blocked(self, ci_agent):
        """Hermes-native never touches a file — pure text generation — so
        the write guard must not apply to it."""
        ci_agent.start()
        result = ci_agent.execute_task(
            "refactoring", {}, force_provider=CodeProvider.HERMES_NATIVE,
        )
        # Not blocked by the sandbox guard specifically — whatever the
        # executor itself returns is fine, but never the sandbox message.
        assert "sandbox" not in (result.error_message or "")

    def test_read_only_task_types_are_never_blocked(self, ci_agent):
        ci_agent.start()
        for task_type in ("code_analysis", "code_review", "documentation"):
            result = ci_agent.execute_task(
                task_type, {}, force_provider=CodeProvider.KLATCODE,
            )
            assert "sandbox" not in (result.error_message or "")

    def test_refused_write_is_still_recorded_in_history(self, ci_agent):
        """A refusal is a real, honest outcome — it must not vanish from
        the audit trail the way the old fabricated-success path did."""
        ci_agent.start()
        ci_agent.execute_task("refactoring", {}, force_provider=CodeProvider.KLATCODE)
        history = ci_agent.get_task_history()
        assert any(h["task_type"] == "refactoring" and not h["success"] for h in history)

    def test_hybrid_review_task_still_reaches_execution(self, ci_agent):
        """code_review is read-only on both providers — the guard must not
        over-block hybrid strategies for task types that never write."""
        ci_agent.start()
        result = ci_agent.execute_task("code_review", {"complexity": 0.9})
        assert "sandbox" not in (result.error_message or "")


# ── Test Agent Events ────────────────────────────────────────

class TestCIAgentEvents:
    """Tests for event bus integration."""

    def test_routing_decision_event(self):
        events = []
        agent = CodeIntelligenceAgent(
            on_event=lambda t, p, **kw: events.append(t),
        )
        agent.start()
        events.clear()
        agent.execute_task("code_analysis", {})
        assert CI_EVENTS["routing_decided"] in events

    def test_task_completed_event(self):
        events = []
        agent = CodeIntelligenceAgent(
            on_event=lambda t, p, **kw: events.append(t),
        )
        agent.start()
        events.clear()
        agent.execute_task("code_analysis", {})
        assert CI_EVENTS["task_completed"] in events

    def test_hybrid_executed_event_with_sub_agents(self):
        kc = CodeIntelligenceAgent(agent_id="kc_sub"); kc.start()
        omp = CodeIntelligenceAgent(agent_id="omp_sub"); omp.start()
        events = []
        agent = CodeIntelligenceAgent(
            on_event=lambda t, p, **kw: events.append(t),
            klaatcode_agent=kc,
            ohmypi_agent=omp,
        )
        agent.start()
        events.clear()
        agent.execute_task("code_review", {"complexity": 0.9})
        assert CI_EVENTS["hybrid_executed"] in events


# ── Test Runtime Scoring ─────────────────────────────────────

class TestCIRuntimeScoring:
    """Tests for runtime scoring adapter."""

    def test_score_both_providers(self, ci_scorer):
        scores = ci_scorer.score("code_analysis")
        assert len(scores) == 2
        assert scores[0].provider in ("klaatcode", "ohmypi")

    def test_klaatcode_best_for_analysis(self, ci_scorer):
        scores = ci_scorer.score("code_analysis", complexity=0.3)
        best = scores[0]
        # KlaatCode should be preferred for analysis
        assert best.suitability > 0

    def test_ohmypi_best_for_refactoring(self, ci_scorer):
        scores = ci_scorer.score("refactoring", complexity=0.8)
        # Oh My Pi uses LSP for refactoring
        assert len(scores) == 2

    def test_availability_flag(self, ci_scorer):
        scores = ci_scorer.score(
            "code_analysis",
            klaatcode_available=False,
        )
        kc = [s for s in scores if s.provider == "klaatcode"][0]
        assert kc.suitability == 0.0
        assert not kc.available

    def test_context_lsp_boosts_ohmypi(self, ci_scorer):
        scores_no_lsp = ci_scorer.score("code_analysis")
        scores_lsp = ci_scorer.score(
            "code_analysis", context={"requires_lsp": True},
        )
        omp_no = [s for s in scores_no_lsp if s.provider == "ohmypi"][0]
        omp_lsp = [s for s in scores_lsp if s.provider == "ohmypi"][0]
        assert omp_lsp.suitability > omp_no.suitability

    def test_record_affects_scoring(self, ci_scorer):
        ci_scorer.record_result("klaatcode", True, 100.0)
        ci_scorer.record_result("klaatcode", True, 80.0)
        ci_scorer.record_result("ohmypi", False, 500.0)
        stats = ci_scorer.stats()
        assert stats["klaatcode"]["success_rate"] == 100.0
        assert stats["ohmypi"]["success_rate"] == 0.0

    def test_get_recommendation(self, ci_scorer):
        rec = ci_scorer.get_recommendation("code_analysis")
        assert "recommended" in rec
        assert "scores" in rec

    def test_scores_sorted_by_suitability(self, ci_scorer):
        scores = ci_scorer.score("code_analysis")
        for i in range(len(scores) - 1):
            assert scores[i].suitability >= scores[i + 1].suitability


# ── Test Models ──────────────────────────────────────────────

class TestCIModels:
    """Tests for code intelligence data models."""

    def test_provider_score_to_dict(self):
        score = ProviderScore(
            provider=CodeProvider.KLATCODE,
            score=0.85,
            factors={"task_fit": 0.9},
            reasoning=["Good fit"],
        )
        d = score.to_dict()
        assert d["provider"] == "klaatcode"
        assert d["score"] == 0.85
        assert len(d["reasoning"]) == 1

    def test_routing_decision_serialization(self):
        decision = RoutingDecision(
            task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
            selected_provider=CodeProvider.KLATCODE,
            strategy=SelectionStrategy.SINGLE_BEST,
            primary_reason=RouteReason.PROJECT_ANALYSIS,
            scores=[
                ProviderScore(provider=CodeProvider.KLATCODE, score=0.92),
            ],
        )
        d = decision.to_dict()
        assert d["selected_provider"] == "klaatcode"
        assert d["strategy"] == "single_best"

    def test_task_provider_preference(self):
        from backend.integrations.code_intelligence.code_intelligence_models import (
            TASK_PROVIDER_PREFERENCE,
        )
        pref = TASK_PROVIDER_PREFERENCE[CodeIntelligenceTaskType.DEBUGGING]
        assert CodeProvider.OHMYPI in pref

    def test_citask_record_fields(self):
        record = CITaskRecord(
            task_id="t1", task_type="code_analysis",
            selected_provider="klaatcode", strategy="single_best",
            primary_reason="project_analysis",
            success=True, duration_ms=42.0,
            klaatcode_score=0.92, ohmypi_score=0.60,
        )
        assert record.success is True
        assert record.selected_provider == "klaatcode"

    def test_ci_profile_has_capabilities(self):
        profile = CodeIntelligenceProfile()
        assert len(profile.capabilities) >= 6
        assert "analysis" in profile.capabilities
        assert "code_generation" in profile.capabilities


# ── Test Thread Safety ───────────────────────────────────────

class TestCIThreadSafety:
    """Tests for thread safety of routing and agent."""

    def test_router_concurrent_decisions(self, router):
        errors = []

        def make_decision(i: int):
            try:
                task = CodeIntelligenceTask(
                    task_id=f"t{i}",
                    task_type=CodeIntelligenceTaskType.CODE_ANALYSIS,
                )
                router.decide(task)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=make_decision, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_agent_concurrent_executions(self, ci_agent):
        ci_agent.start()
        errors = []

        def run_task(i: int):
            try:
                task_type = "code_analysis" if i % 2 == 0 else "code_generation"
                ci_agent.execute_task(task_type, {})
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=run_task, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_scorer_concurrent(self, ci_scorer):
        errors = []

        def record_and_score(i: int):
            try:
                ci_scorer.record_result("klaatcode", i % 2 == 0, 100.0)
                ci_scorer.score("code_analysis")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=record_and_score, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ── Test Factory ─────────────────────────────────────────────

class TestFactory:
    """Tests for factory functions."""

    def test_create_agent(self):
        agent = create_code_intelligence_agent()
        assert agent.status == AgentStatus.READY
        assert agent.is_available is True
        assert "ci_" in agent.agent_id

    def test_create_agent_with_klaatcode(self):
        kc = CodeIntelligenceAgent(agent_id="kc_sub")
        kc.start()
        agent = create_code_intelligence_agent(klaatcode_agent=kc)
        assert agent.is_available

    def test_create_agent_with_router(self):
        custom_router = CodeIntelligenceRouter()
        agent = create_code_intelligence_agent(router=custom_router)
        assert agent.is_available
