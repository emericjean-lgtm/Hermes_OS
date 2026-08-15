"""Tests for Autonomous Agentic Core (HOS-063).

Covers: models, interpreter, decision engine, orchestrator,
guard, memory loop, engine facade, API, EventBus, thread safety,
and full mission simulation (100+ tests).
"""

import random
import threading

import pytest


from backend.autonomous.autonomous_models import (
    AUTONOMOUS_EVENTS,
    AutonomousDecision,
    AutonomousGoal,
    AutonomousReport,
    AutonomousSession,
    DecisionType,
    GOAL_PATTERNS,
    GoalStatus,
)
from backend.autonomous.autonomous_interpreter import AutonomousInterpreter
from backend.autonomous.decision_engine import DecisionEngine
from backend.autonomous.autonomous_guard import AutonomousGuard, GuardVerdict
from backend.autonomous.autonomous_memory_loop import AutonomousMemoryLoop
from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
from backend.autonomous.autonomous_engine import AutonomousEngine
from backend.autonomous.routes import handle_start_goal, handle_get_status, handle_get_goal, handle_cancel_goal


# ======================================================================
# 1. Models
# ======================================================================

class TestAutonomousModels:

    def test_goal_all_statuses(self):
        for status in GoalStatus:
            g = AutonomousGoal(goal_id="g1", status=status)
            assert g.status == status

    def test_goal_to_dict(self):
        g = AutonomousGoal(goal_id="g1", user_request="Test request", interpreted_goal="Test interpretation")
        d = g.to_dict()
        assert d["goal_id"] == "g1"
        assert d["user_request"] == "Test request"

    def test_decision_defaults(self):
        d = AutonomousDecision(decision_id="d1", decision_type=DecisionType.AGENT_SELECTION)
        assert d.confidence == 0.0
        assert d.selected_option == ""

    def test_decision_to_dict(self):
        d = AutonomousDecision(decision_id="d1", decision_type=DecisionType.RUNTIME_SELECTION,
                               confidence=0.85, selected_option="ktransformers",
                               reason="Best runtime")
        d2 = d.to_dict()
        assert d2["decision_type"] == "runtime_selection"
        assert d2["confidence"] == 0.85

    def test_session_to_dict(self):
        s = AutonomousSession(session_id="s1", goal_id="g1", active_agents=["agent1", "agent2"])
        d = s.to_dict()
        assert len(d["active_agents"]) == 2

    def test_report_defaults(self):
        r = AutonomousReport(goal_id="g1", user_request="test")
        assert r.total_duration_ms == 0.0
        assert r.success is False

    def test_events_all_prefixed(self):
        for key, evt in AUTONOMOUS_EVENTS.items():
            assert evt.startswith("autonomous.")

    def test_goal_patterns(self):
        assert "web_app" in GOAL_PATTERNS
        assert GOAL_PATTERNS["web_app"]["domain"] == "web"


# ======================================================================
# 2. Interpreter
# ======================================================================

class TestAutonomousInterpreter:

    def test_interpret_web_request(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Create a web application for managing maintenance operations")
        assert goal.domain == "web"
        assert goal.status == GoalStatus.ANALYZING
        assert goal.goal_id.startswith("goal_")

    def test_interpret_backend_request(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Build a REST API for user authentication")
        assert goal.domain == "backend"

    def test_interpret_data_request(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Analyze customer data and build a pipeline")
        assert goal.domain == "data"

    def test_interpret_refactor_request(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Refactor the authentication module to use JWT")
        assert goal.domain == "code"

    def test_interpret_debug_request(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Debug the login endpoint timeout issue")
        assert goal.domain == "code"

    def test_interpret_language_python(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Create a Flask API for user management")
        assert goal.language == "python"

    def test_interpret_language_typescript(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Build a Next.js frontend with TypeScript")
        assert goal.language == "typescript"

    def test_interpret_priority_urgent(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("URGENT: Fix the production security vulnerability")
        assert goal.contraints.get("priority") == "high"

    def test_interpret_complexity_estimation(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Simple task")
        assert goal.complexity > 0

    def test_interpret_high_complexity(self):
        """A complex request must score above the 0.4 band.

        The RNG is seeded because ``_estimate_complexity`` adds
        ``random.uniform(-0.1, 0.1)`` to its base score. For this request the
        base is 0.45 (0.3 + 0.15 for the "complete"/"microservices" keywords;
        the string is 113 chars, so neither length bonus applies), which means
        the assertion below failed for any draw under -0.05 — 25% of runs,
        measured at 24.8% over 4000 draws. It passed or failed purely on where
        the global random stream happened to be, so any change in test ordering
        flipped it.

        Seeding rather than widening the assertion keeps the test meaningful:
        0.4 is the band this request is supposed to clear, and the jitter is an
        implementation detail of the estimator, not part of the contract.
        """
        random.seed(2)  # draw lands at 0.5412, comfortably clear of the band
        interp = AutonomousInterpreter()
        goal = interp.interpret("Create a complete full-stack microservices application with authentication, payments, and real-time notifications")
        assert goal.complexity > 0.4

    def test_interpret_history_tracked(self):
        interp = AutonomousInterpreter()
        interp.interpret("Goal one")
        interp.interpret("Goal two")
        assert len(interp.get_history()) == 2


# ======================================================================
# 3. Decision Engine
# ======================================================================

class TestDecisionEngine:

    def test_select_agent(self):
        de = DecisionEngine()
        d = de.select_agent("code_analysis", {"domain": "web"})
        assert d.decision_type == DecisionType.AGENT_SELECTION
        assert d.confidence > 0
        assert d.selected_option in ("klaatcode", "ohmypi", "code_intelligence", "mission_planner")

    def test_select_runtime(self):
        de = DecisionEngine()
        d = de.select_runtime("code_analysis", 0.7)
        assert d.decision_type == DecisionType.RUNTIME_SELECTION

    def test_select_runtime_without_orchestrator_never_names_a_phantom_runtime(self):
        """Unwired, this used to always pick one of three names —
        "ktransformers", "default_llm", "local_model" — that nothing in the
        codebase has ever registered. The fallback must name a runtime that
        could plausibly exist, not one of the old fixed fantasy options."""
        de = DecisionEngine()
        d = de.select_runtime("general", 0.3)
        assert d.selected_option not in ("ktransformers", "default_llm", "local_model")

    def test_select_runtime_with_orchestrator_uses_the_real_registry(self):
        """Wired, the decision must be built from whatever the orchestrator
        actually knows about — not the hardcoded list, regardless of what
        that list happens to contain."""
        class _FakeOrchestrator:
            def get_stats(self):
                return {"runtime_ids": ["a-real-runtime"]}

        de = DecisionEngine()
        de.set_runtime_orchestrator(_FakeOrchestrator())
        d = de.select_runtime("general", 0.3)
        assert d.selected_option == "a-real-runtime"

    def test_select_tool(self):
        de = DecisionEngine()
        d = de.select_tool("code_analysis", {"language": "python"})
        assert d.decision_type == DecisionType.TOOL_SELECTION

    def test_select_skill(self):
        de = DecisionEngine()
        d = de.select_skill("code_analysis", "web")
        assert d.decision_type == DecisionType.SKILL_SELECTION

    def test_decisions_tracked(self):
        de = DecisionEngine()
        de.select_agent("code_analysis", {})
        de.select_runtime("code_analysis", 0.5)
        de.select_tool("code_analysis", {})
        assert len(de.get_decisions()) == 3

    def test_stats(self):
        de = DecisionEngine()
        de.select_agent("code_analysis", {})
        stats = de.stats()
        assert stats["total_decisions"] >= 1
        assert "avg_confidence" in stats

    def test_agent_for_code_analysis(self):
        de = DecisionEngine()
        d = de.select_agent("diagnostics", {})
        assert d.confidence > 0

    def test_agent_for_refactoring(self):
        de = DecisionEngine()
        d = de.select_agent("refactoring", {})
        assert d.confidence > 0


# ======================================================================
# 4. Autonomous Guard
# ======================================================================

class TestAutonomousGuard:

    def test_allow_normal_action(self):
        g = AutonomousGuard()
        assert g.check_action("goal.execute", "goal/test") == GuardVerdict.ALLOW

    def test_block_security_modify(self):
        g = AutonomousGuard()
        assert g.check_action("security.modify", "security/policy") == GuardVerdict.BLOCK

    def test_block_permission_change(self):
        g = AutonomousGuard()
        assert g.check_action("permission.change", "agent1/tool/exec") == GuardVerdict.BLOCK

    def test_block_mass_deletion(self):
        g = AutonomousGuard()
        assert g.check_action("mass_deletion", "memory/*") == GuardVerdict.BLOCK

    def test_block_policy_override(self):
        g = AutonomousGuard()
        assert g.check_action("policy.override", "policy/engine") == GuardVerdict.BLOCK

    def test_blocked_actions_tracked(self):
        g = AutonomousGuard()
        g.check_action("security.modify", "test")
        g.check_action("permission.change", "test")
        assert len(g.get_blocked_actions()) == 2

    def test_stats(self):
        g = AutonomousGuard()
        stats = g.stats()
        assert stats["total_blocked"] >= 0


# ======================================================================
# 5. Memory Loop
# ======================================================================

class TestAutonomousMemoryLoop:

    def test_process_report(self):
        ml = AutonomousMemoryLoop()
        report = AutonomousReport(goal_id="g1", user_request="test", success=True)
        result = ml.process_report(report)
        assert result["lessons_count"] >= 0

    def test_learnings_tracked(self):
        ml = AutonomousMemoryLoop()
        r1 = AutonomousReport(goal_id="g1", user_request="test", success=True, lessons=["lesson1"])
        r2 = AutonomousReport(goal_id="g2", user_request="test2", success=False, lessons=["err1"])
        ml.process_report(r1); ml.process_report(r2)
        assert len(ml.get_learnings()) == 2

    def test_learning_summary(self):
        ml = AutonomousMemoryLoop()
        ml.process_report(AutonomousReport(goal_id="g1", user_request="test", success=True, lessons=["l1"]))
        ml.process_report(AutonomousReport(goal_id="g2", user_request="test2", success=False))
        summary = ml.get_learning_summary()
        assert summary["missions"] == 2
        assert summary["success_rate"] == 50.0


# ======================================================================
# 6. Orchestrator
# ======================================================================

class TestAutonomousOrchestrator:

    def test_start_goal_creates_goal(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Create a web application")
        assert goal.user_request == "Create a web application"
        assert goal.status in (GoalStatus.COMPLETED, GoalStatus.FAILED)

    def test_start_goal_domain_detected(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Build a REST API")
        assert goal.domain in ("backend", "web")

    def test_report_carries_the_generated_text_not_just_its_length(self):
        """The report used to keep only the task's own title and a character
        count (`{"task": t.title, "chars": len(...)}`) — real tokens were spent
        against a real runtime, but what the model actually said was discarded
        before it ever reached the API or the Cockpit."""
        from tests.support.fake_inference import FAKE_COMPLETION

        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Write a function")
        assert goal.status == GoalStatus.COMPLETED
        report = orch.get_report(goal.goal_id)
        assert report is not None
        outputs = report.results["outputs"]
        assert outputs, "a completed goal must report at least one output"
        assert outputs[0]["content"] == FAKE_COMPLETION

    def test_model_adapter_off_by_default_is_a_safe_noop(self):
        """set_model_adapter() is never called by these bare-constructor
        tests — this pins that a goal still completes normally when no
        adapter is wired, the same isolation every other test here relies
        on."""
        orch = AutonomousOrchestrator()
        assert orch._model_adapter is None
        goal = orch.start_goal("Write a function")
        assert goal.status == GoalStatus.COMPLETED

    def test_model_adapter_receives_real_feedback_not_a_fabrication(self):
        """ModelAutonomousAdapter.record_feedback() existed since HOS-065B
        and was never called by anything — a goal's model choice and
        outcome went nowhere. _make_task_executor's model_for callback
        picks the model that actually runs; this confirms that same real
        choice (not a placeholder) reaches record_feedback()."""
        calls = []

        class _FakeAdapter:
            def record_feedback(self, feedback):
                calls.append(feedback)

        orch = AutonomousOrchestrator()
        orch.set_model_adapter(_FakeAdapter())
        goal = orch.start_goal("Write a function")
        assert goal.status == GoalStatus.COMPLETED

        assert len(calls) == 1
        feedback = calls[0]
        assert feedback.goal_id == goal.goal_id
        assert feedback.model_id == "qwen3.5:4b"  # RealTaskExecutor's default
        assert feedback.success is True
        assert feedback.duration_ms > 0
        assert feedback.tokens_used > 0

    def test_report_includes_the_real_models_used(self):
        """results.models_used surfaces the specific model tag Model
        Intelligence picked (e.g. "qwen3.5:4b") — previously discarded inside
        RealTaskExecutor/MissionExecutor before reaching the report, leaving
        only the runtime provider name ("ollama") in runtimes_used."""
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Write a function")
        report = orch.get_report(goal.goal_id)
        assert report is not None
        assert report.results["models_used"] == ["qwen3.5:4b"]

    def test_broken_model_adapter_does_not_fail_the_goal(self):
        """A reporting failure must not turn an already-completed goal into
        a failed one — the same discipline as _emit()/_report_execution()
        elsewhere in this codebase."""

        class _BrokenAdapter:
            def record_feedback(self, feedback):
                raise RuntimeError("boom")

        orch = AutonomousOrchestrator()
        orch.set_model_adapter(_BrokenAdapter())
        goal = orch.start_goal("Write a function")
        assert goal.status == GoalStatus.COMPLETED

    def test_pause_goal(self):
        orch = AutonomousOrchestrator()
        # Create a new object directly for pause testing
        from backend.autonomous.autonomous_models import AutonomousGoal, GoalStatus
        import time
        g = AutonomousGoal(goal_id=f"pause_test_{int(time.time())}", user_request="pause test",
                          status=GoalStatus.EXECUTING)
        orch._goals[g.goal_id] = g
        assert orch.pause_goal(g.goal_id) is True

    def test_resume_goal(self):
        orch = AutonomousOrchestrator()
        from backend.autonomous.autonomous_models import AutonomousGoal, GoalStatus
        import time
        g = AutonomousGoal(goal_id=f"resume_test_{int(time.time())}", user_request="resume test",
                          status=GoalStatus.PAUSED)
        orch._goals[g.goal_id] = g
        assert orch.resume_goal(g.goal_id) is True

    def test_cancel_goal(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Quick task")
        assert orch.cancel_goal(goal.goal_id)

    def test_get_goal(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test goal")
        retrieved = orch.get_goal(goal.goal_id)
        assert retrieved is not None
        assert retrieved.user_request == "Test goal"

    def test_get_session(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test")
        session = orch.get_session(goal.goal_id)
        assert session is not None

    def test_get_report(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test")
        report = orch.get_report(goal.goal_id)
        assert report is not None

    def test_get_status(self):
        orch = AutonomousOrchestrator()
        orch.start_goal("First goal")
        orch.start_goal("Second goal")
        status = orch.get_status()
        assert status["total_goals"] >= 2

    def test_goal_status_flow(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test flow")
        assert goal.status in (GoalStatus.COMPLETED, GoalStatus.FAILED)

    def test_events_published(self):
        events = []
        orch = AutonomousOrchestrator(on_event=lambda t, p, **kw: events.append(t))
        orch.start_goal("Event test")
        assert AUTONOMOUS_EVENTS["goal_received"] in events
        assert AUTONOMOUS_EVENTS["goal_analyzed"] in events

    def test_decisions_made(self):
        orch = AutonomousOrchestrator()
        orch.start_goal("Decision test")
        decisions = orch.decisions.get_decisions()
        assert len(decisions) >= 3  # agent + runtime + tool


# ======================================================================
# 7. Engine Facade
# ======================================================================

class TestAutonomousEngine:

    def test_start_goal(self):
        engine = AutonomousEngine()
        result = engine.start_goal("Test from engine")
        assert result["user_request"] == "Test from engine"
        assert "goal_id" in result

    def test_get_status(self):
        engine = AutonomousEngine()
        engine.start_goal("Status test")
        status = engine.get_status()
        assert "total_goals" in status

    def test_pause_resume_goal(self):
        engine = AutonomousEngine()
        from backend.autonomous.autonomous_models import AutonomousGoal, GoalStatus
        import time
        g = AutonomousGoal(goal_id=f"engine_pause_{int(time.time())}", user_request="pause",
                          status=GoalStatus.EXECUTING)
        engine._orchestrator._goals[g.goal_id] = g
        pause = engine.pause_goal(g.goal_id)
        assert pause["success"] is True
        resume = engine.resume_goal(g.goal_id)
        assert resume["success"] is True

    def test_cancel_goal(self):
        engine = AutonomousEngine()
        goal = engine.start_goal("Cancel test")
        result = engine.cancel_goal(goal["goal_id"])
        assert result["success"] is True

    def test_get_timeline(self):
        engine = AutonomousEngine()
        goal = engine.start_goal("Timeline test")
        tl = engine.get_timeline(goal["goal_id"])
        assert "timeline" in tl

    def test_get_report(self):
        engine = AutonomousEngine()
        goal = engine.start_goal("Report test")
        report = engine.get_report(goal["goal_id"])
        assert report is not None


# ======================================================================
# 8. API Routes
# ======================================================================

class TestAPIRoutes:
    """Ces routes doivent partir d'un moteur neuf, pas de celui du conteneur.

    `backend/autonomous/routes.py` garde son moteur dans un global de
    module, et `create_autonomous_routes()` — appelé par le composition
    root — l'y installe pleinement câblé : vrai planificateur, vrai
    exécuteur de graphe, vrais exécuteurs de tâches. N'importe quel test
    antérieur qui construit l'application le laisse donc en place.

    Seuls, ces quatre tests passaient en moins d'une seconde. Dans la suite
    complète, `handle_start_goal` héritait du moteur câblé, exécutait un
    vrai DAG et **pendait** sur un `as_completed` sans délai — après avoir
    laissé derrière lui des dizaines de fils `hermes-task-executor`. Le
    vidage de pile en comptait 55 au moment du blocage (HOS-112).

    Un test qui change de comportement selon ce qui a tourné avant ne
    mesure pas ce qu'il prétend mesurer.
    """

    @pytest.fixture(autouse=True)
    def _moteur_neuf(self):
        from backend.autonomous.routes import reset_engine

        reset_engine()
        yield
        reset_engine()

    def test_handle_start_goal(self):
        result = handle_start_goal({"user_request": "API test goal"})
        assert result["user_request"] == "API test goal"

    def test_handle_get_status(self):
        status = handle_get_status()
        assert "total_goals" in status

    def test_handle_get_goal(self):
        result = handle_start_goal({"user_request": "Get me goal"})
        goal = handle_get_goal(result["goal_id"])
        assert goal is not None
        assert goal["user_request"] == "Get me goal"

    def test_handle_cancel_goal(self):
        result = handle_start_goal({"user_request": "Cancel me"})
        cancel = handle_cancel_goal(result["goal_id"])
        assert cancel["success"] is True


# ======================================================================
# 9. Thread Safety
# ======================================================================

class TestAutonomousThreadSafety:

    def test_concurrent_goals(self):
        engine = AutonomousEngine()
        errors = []
        def start_goal(i: int):
            try:
                engine.start_goal(f"Concurrent goal {i}")
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=start_goal, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_orchestrator(self):
        orch = AutonomousOrchestrator()
        errors = []
        def run(i: int):
            try:
                g = orch.start_goal(f"Thread {i}")
                orch.pause_goal(g.goal_id)
                orch.resume_goal(g.goal_id)
                orch.get_status()
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=run, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_decision_engine(self):
        de = DecisionEngine()
        errors = []
        def decide(i: int):
            try:
                de.select_agent("code_analysis", {})
                de.select_runtime("code_analysis", 0.5)
                de.stats()
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=decide, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_interpreter(self):
        interp = AutonomousInterpreter()
        errors = []
        def interpret(i: int):
            try:
                interp.interpret(f"Goal number {i}")
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=interpret, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []


# ======================================================================
# 10. Full Mission Simulation
# ======================================================================

class TestFullMissionSimulation:

    def test_full_web_mission(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Create a web application for managing maintenance operations", {
            "priority": "high",
        })
        assert goal.domain == "web"
        assert goal.priority == "high"
        assert goal.status in (GoalStatus.COMPLETED, GoalStatus.FAILED)
        assert len(goal.goal_id) > 0

    def test_full_debug_mission(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Debug the login endpoint timeout in production")
        assert goal.domain in ("code", "backend")

    def test_full_api_mission(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Build a REST API with authentication endpoints")
        assert goal.domain in ("backend", "web")
        assert goal.status in (GoalStatus.COMPLETED, GoalStatus.FAILED)

    def test_full_refactor_mission(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Refactor the database layer to use connection pooling")
        assert goal.domain == "code"

    def test_mission_generates_report(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test report generation")
        report = orch.get_report(goal.goal_id)
        assert report is not None
        assert report.user_request == "Test report generation"
        assert len(report.decisions) > 0

    def test_mission_timeline(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Test timeline")
        session = orch.get_session(goal.goal_id)
        assert session is not None
        assert len(session.timeline) >= 1

    def test_mission_agents_selected(self):
        orch = AutonomousOrchestrator()
        goal = orch.start_goal("Agent selection test")
        decisions = orch.decisions.get_decisions()
        agent_dec = [d for d in decisions if d.decision_type == DecisionType.AGENT_SELECTION]
        assert len(agent_dec) >= 1

    def test_mission_success_rate(self):
        results = []
        for _ in range(10):
            orch = AutonomousOrchestrator()
            goal = orch.start_goal(f"Test run simulation")
            results.append(goal.status == GoalStatus.COMPLETED)
        success_rate = sum(results) / len(results)
        assert success_rate > 0.5  # 85% success rate configured
