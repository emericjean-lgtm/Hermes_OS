"""Tests for HOS-067 — Autonomous OS real-wiring:

* the real multi-node DAG path (planner + graph executor injected),
* the risk-based Aegis gate (AegisSecurityAdapter, local_path/repository/
  security_required triggers, REVIEW -> PAUSED not FAILED),
* real per-node decisions derived from the plan (no DecisionEngine fakes),
* real cross-memory retrieval before planning.

Fully hermetic: fakes stand in for MissionPlanner/GraphExecutor/AegisEngine/
MemoryManager, no real Ollama or filesystem access needed.
"""
from __future__ import annotations

from backend.autonomous.autonomous_guard import AegisSecurityAdapter, AutonomousGuard, GuardVerdict
from backend.autonomous.autonomous_interpreter import AutonomousInterpreter
from backend.autonomous.autonomous_models import AutonomousDecision, DecisionType, GoalStatus
from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
from backend.mission.mission_models import Mission, MissionNode, MissionStatus, NodeStatus
from backend.mission.planner.planner_models import (
    PlanningResult,
    PlanningStage,
    RuntimeRecommendation,
    TaskBreakdown,
    TaskCategory,
)


# ── Fakes ────────────────────────────────────────────────────────────

class _FakePlanner:
    """Stands in for MissionPlanner: plan()/build_mission() only."""

    def __init__(self, breakdowns, runtime_recs=None):
        self._breakdowns = breakdowns
        self._runtime_recs = runtime_recs or {}
        self.last_request = None

    def plan(self, request):
        self.last_request = request
        result = PlanningResult(request_id=request.request_id)
        result.task_breakdowns = self._breakdowns
        result.runtime_recommendations = self._runtime_recs
        result.current_stage = PlanningStage.COMPLETED
        return result

    def build_mission(self, result, title="", objective=""):
        nodes = [
            MissionNode(node_id=b.task_id, title=b.title,
                       required_skills=b.required_skills, preferred_runtime="qwen3:4b")
            for b in result.task_breakdowns
        ]
        return Mission(title=title, objective=objective, nodes=nodes, edges=[])


class _EmptyPlanner:
    """A planner whose decomposition produces nothing usable."""

    def plan(self, request):
        result = PlanningResult(request_id=request.request_id)
        result.current_stage = PlanningStage.FAILED
        result.errors = ["no tasks could be produced"]
        return result

    def build_mission(self, result, title="", objective=""):
        raise AssertionError("build_mission should not be called when planning produced nothing")


class _FakeGraphExecutor:
    """Stands in for GraphExecutor: build_graph/start_mission/execute_step."""

    def __init__(self, *, all_succeed: bool = True, build_issues=None):
        self._all_succeed = all_succeed
        self._build_issues = build_issues or []

    def build_graph(self, mission, nodes, edges):
        mission.nodes = nodes
        mission.edges = edges
        return list(self._build_issues)

    def start_mission(self, mission) -> bool:
        mission.status = MissionStatus.RUNNING
        return True

    def execute_step(self, mission) -> int:
        stepped = 0
        for n in mission.nodes:
            if n.status == NodeStatus.PENDING:
                n.status = NodeStatus.COMPLETED if self._all_succeed else NodeStatus.FAILED
                n.actual_duration_ms = 12.0
                n.result_summary = f"fake output for {n.title}"
                n.preferred_runtime = "ollama"
                stepped += 1
        if stepped:
            mission.status = MissionStatus.COMPLETED if self._all_succeed else MissionStatus.FAILED
        return stepped


def _breakdown(task_id: str, title: str, category=TaskCategory.IMPLEMENTATION,
              required_skills=None) -> TaskBreakdown:
    return TaskBreakdown(task_id=task_id, title=title, category=category,
                         required_skills=required_skills or [])


# ── Real DAG path ────────────────────────────────────────────────────

class TestRealDagPath:
    def test_uses_dag_when_planner_and_executor_wired(self):
        breakdowns = [_breakdown("t1", "Analyze the module", TaskCategory.ANALYSIS)]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns),
            graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("Analyze the auth module")
        assert goal.status == GoalStatus.COMPLETED
        report = orch.get_report(goal.goal_id)
        assert report.results["tasks_total"] == 1
        assert report.results["tasks_completed"] == 1
        assert report.results["outputs"][0]["content"] == "fake output for Analyze the module"

    def test_multi_node_plan_all_reported(self):
        breakdowns = [
            _breakdown("t1", "Design schema", TaskCategory.DESIGN),
            _breakdown("t2", "Implement models", TaskCategory.IMPLEMENTATION),
            _breakdown("t3", "Write tests", TaskCategory.TESTING),
        ]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns), graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("Build a database layer")
        report = orch.get_report(goal.goal_id)
        assert report.results["tasks_total"] == 3
        assert report.results["tasks_completed"] == 3

    def test_failed_node_fails_the_goal_honestly(self):
        breakdowns = [_breakdown("t1", "Do the thing")]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns),
            graph_executor=_FakeGraphExecutor(all_succeed=False),
        )
        goal = orch.start_goal("Do the thing")
        assert goal.status == GoalStatus.FAILED
        report = orch.get_report(goal.goal_id)
        assert report.results["tasks_failed"] == 1

    def test_empty_plan_fails_honestly_no_fabricated_task(self):
        orch = AutonomousOrchestrator(
            mission_planner=_EmptyPlanner(), graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("An impossible request")
        assert goal.status == GoalStatus.FAILED

    def test_invalid_graph_reported_not_silently_dropped(self):
        breakdowns = [_breakdown("t1", "Task with bad deps")]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns),
            graph_executor=_FakeGraphExecutor(build_issues=["cycle detected"]),
        )
        goal = orch.start_goal("Broken plan")
        assert goal.status == GoalStatus.FAILED
        report = orch.get_report(goal.goal_id)
        assert "cycle detected" in report.execution_summary

    def test_fallback_to_legacy_path_when_not_wired(self):
        """No planner/graph_executor -> exactly today's single-task path,
        proven by the fact the bare-constructor suite (tests/autonomous/
        test_autonomous_core.py) passes unmodified."""
        orch = AutonomousOrchestrator()
        assert orch.mission_planner is None
        assert orch.graph_executor is None
        goal = orch.start_goal("Write a function")
        assert goal.status == GoalStatus.COMPLETED

    def test_repository_and_branch_reach_the_planning_request(self):
        breakdowns = [_breakdown("t1", "Fix the bug")]
        planner = _FakePlanner(breakdowns)
        orch = AutonomousOrchestrator(mission_planner=planner, graph_executor=_FakeGraphExecutor())
        orch.start_goal("Fix the login bug", {
            "repository": "https://github.com/example/repo", "branch": "main",
        })
        assert planner.last_request.repository == "https://github.com/example/repo"
        assert planner.last_request.branch == "main"

    def test_knowledge_context_reaches_the_planning_request_specification(self):
        breakdowns = [_breakdown("t1", "Task")]
        planner = _FakePlanner(breakdowns)

        class _FakeMemory:
            def recommend_for_mission(self, mission_type, tags):
                return {
                    "similar_missions": 3, "similar_success_rate": 66.7,
                    "recommended_models": ["qwen3:4b"], "best_practices": ["write tests first"],
                    "frequent_errors": [],
                }

        orch = AutonomousOrchestrator(mission_planner=planner, graph_executor=_FakeGraphExecutor())
        orch.interpreter.set_memory_manager(_FakeMemory())
        orch.start_goal("Refactor the auth module")
        assert "3 similar past mission" in planner.last_request.specification


class TestRealDecisionsFromPlan:
    def test_agent_decision_names_a_real_registered_agent(self):
        """config/agents.yaml's real 10 agents, not DecisionEngine's
        unregistered "klaatcode"/"ohmypi"/"code_intelligence" names."""
        real_agents = {"hermes_prime", "hermes_swift", "atlas", "minerva",
                       "hermes_scribe", "aegis", "kronos", "hermes_eyes", "veritas", "echo"}
        breakdowns = [_breakdown("t1", "Write the docs", TaskCategory.DOCUMENTATION)]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns), graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("Document the API")
        report = orch.get_report(goal.goal_id)
        agent_decisions = [d for d in report.decisions if d["decision_type"] == "agent_selection"]
        assert agent_decisions
        assert agent_decisions[0]["selected"] in real_agents
        assert agent_decisions[0]["selected"] == "hermes_scribe"  # documentation -> the writing agent

    def test_runtime_decision_uses_the_real_recommendation_reasoning(self):
        breakdowns = [_breakdown("t1", "Implement the feature")]
        rec = RuntimeRecommendation(
            task_id="t1", model_name="qwen3-coder:30b", confidence=0.8,
            reasoning="Category 'implementation' maps to profile 'coding'.",
        )
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns, {"t1": rec}),
            graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("Implement the feature")
        report = orch.get_report(goal.goal_id)
        runtime_decisions = [d for d in report.decisions if d["decision_type"] == "runtime_selection"]
        assert runtime_decisions
        assert runtime_decisions[0]["selected"] == "qwen3-coder:30b"
        assert runtime_decisions[0]["reason"] == rec.reasoning

    def test_skill_decision_present_when_task_requires_skills(self):
        breakdowns = [_breakdown("t1", "Task", required_skills=["testing", "python"])]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns), graph_executor=_FakeGraphExecutor(),
        )
        goal = orch.start_goal("Task with skills")
        report = orch.get_report(goal.goal_id)
        skill_decisions = [d for d in report.decisions if d["decision_type"] == "skill_selection"]
        assert skill_decisions
        assert skill_decisions[0]["selected"] == "testing"


# ── AegisSecurityAdapter ─────────────────────────────────────────────

class TestAegisSecurityAdapter:
    def _matrix_engine(self, autonomy_level="low", allowed_paths=None):
        from backend.security.aegis_engine import AegisEngine
        from backend.security.permission_matrix import PermissionMatrix

        config = {
            "autonomy_level": autonomy_level,
            "action_categories": {
                "autonomous_goal_execute": {
                    "mutating": True, "path_based": False,
                    "mandatory_validation": False, "min_autonomy_for_auto_allow": "medium",
                },
                "file_read": {"mutating": False, "path_based": True, "mandatory_validation": False},
            },
        }
        return AegisEngine(PermissionMatrix(config), allowed_paths or [])

    def test_allow_maps_through(self):
        engine = self._matrix_engine(autonomy_level="high")
        adapter = AegisSecurityAdapter(engine)
        result = adapter.check_access(
            principal_id="autonomous", resource_type="system", resource_id="goal/x",
            operation="autonomous_goal_execute", context={},
        )
        assert result["allowed"] is True
        assert result["requires_review"] is False

    def test_require_validation_maps_to_review(self):
        """REQUIRE_HUMAN_VALIDATION is not a denial — allowed=True lets
        AutonomousGuard.check_action() reach its own requires_review check
        (it tests `allowed` before `requires_review`, so a DENY-shaped
        allowed=False would short-circuit straight to BLOCK instead)."""
        engine = self._matrix_engine(autonomy_level="low")
        adapter = AegisSecurityAdapter(engine)
        result = adapter.check_access(
            principal_id="autonomous", resource_type="system", resource_id="goal/x",
            operation="autonomous_goal_execute", context={},
        )
        assert result["allowed"] is True
        assert result["requires_review"] is True

    def test_path_outside_whitelist_denied(self, tmp_path):
        engine = self._matrix_engine(autonomy_level="high", allowed_paths=[str(tmp_path / "allowed")])
        adapter = AegisSecurityAdapter(engine)
        result = adapter.check_access(
            principal_id="autonomous", resource_type="path", resource_id="x",
            operation="file_read", context={"target_path": str(tmp_path / "elsewhere")},
        )
        assert result["allowed"] is False
        assert result["requires_review"] is False


# ── Risk-based gating in the orchestrator ────────────────────────────

class TestRiskBasedGate:
    def _wired_guard_orchestrator(self, *, autonomy_level="low", allowed_paths=None):
        from backend.security.aegis_engine import AegisEngine
        from backend.security.permission_matrix import PermissionMatrix

        config = {
            "autonomy_level": autonomy_level,
            "action_categories": {
                "autonomous_goal_execute": {
                    "mutating": True, "path_based": False,
                    "mandatory_validation": False, "min_autonomy_for_auto_allow": "medium",
                },
                "file_read": {"mutating": False, "path_based": True, "mandatory_validation": False},
            },
        }
        engine = AegisEngine(PermissionMatrix(config), allowed_paths or [])
        breakdowns = [_breakdown("t1", "Task")]
        orch = AutonomousOrchestrator(
            mission_planner=_FakePlanner(breakdowns), graph_executor=_FakeGraphExecutor(),
        )
        orch.guard.set_security_engine(AegisSecurityAdapter(engine))
        return orch

    def test_plain_goal_skips_the_gate_entirely(self):
        """No local_path/repository/security keyword -> no real-world
        footprint today, so no Aegis check at all — must not be blocked by
        the shipped low autonomy_level, or the tab would do nothing by
        default."""
        orch = self._wired_guard_orchestrator(autonomy_level="low")
        goal = orch.start_goal("Write a haiku about databases")
        assert goal.status == GoalStatus.COMPLETED

    def test_goal_bound_to_local_path_requires_review_at_low_autonomy(self, tmp_path):
        orch = self._wired_guard_orchestrator(autonomy_level="low", allowed_paths=[str(tmp_path)])
        goal = orch.start_goal("Fix the bug", {"local_path": str(tmp_path)})
        assert goal.status == GoalStatus.PAUSED

    def test_goal_bound_to_local_path_allowed_at_high_autonomy(self, tmp_path):
        orch = self._wired_guard_orchestrator(autonomy_level="high", allowed_paths=[str(tmp_path)])
        goal = orch.start_goal("Fix the bug", {"local_path": str(tmp_path)})
        assert goal.status == GoalStatus.COMPLETED

    def test_local_path_outside_whitelist_fails_before_planning(self, tmp_path):
        orch = self._wired_guard_orchestrator(
            autonomy_level="high", allowed_paths=[str(tmp_path / "allowed")],
        )
        goal = orch.start_goal("Fix the bug", {"local_path": str(tmp_path / "elsewhere")})
        assert goal.status == GoalStatus.FAILED

    def test_security_flagged_request_requires_review(self):
        orch = self._wired_guard_orchestrator(autonomy_level="low")
        goal = orch.start_goal("Make sure this endpoint is secure")
        assert goal.contraints.get("security_required") is True
        assert goal.status == GoalStatus.PAUSED


# ── Interpreter memory retrieval (Phase D) ───────────────────────────

class TestInterpreterKnowledgeRetrieval:
    def test_no_memory_manager_leaves_context_empty(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Write a function")
        assert goal.knowledge_context == ""

    def test_uses_recommend_for_mission_not_the_old_broken_search_call(self):
        calls = []

        class _FakeMemory:
            def recommend_for_mission(self, mission_type, tags):
                calls.append((mission_type, tags))
                return {"similar_missions": 0}

        interp = AutonomousInterpreter()
        interp.set_memory_manager(_FakeMemory())
        goal = interp.interpret("Build a REST API")
        assert calls, "recommend_for_mission must actually be called"
        assert goal.knowledge_context == ""  # no similar missions -> honest empty summary

    def test_real_history_produces_a_real_summary(self):
        class _FakeMemory:
            def recommend_for_mission(self, mission_type, tags):
                return {
                    "similar_missions": 2, "similar_success_rate": 100.0,
                    "recommended_models": ["qwen3.5:9b"],
                    "best_practices": ["validate inputs early"],
                    "frequent_errors": ["timeout on large payloads"],
                }

        interp = AutonomousInterpreter()
        interp.set_memory_manager(_FakeMemory())
        goal = interp.interpret("Build another REST API")
        assert "2 similar past mission" in goal.knowledge_context
        assert "validate inputs early" in goal.knowledge_context
        assert "timeout on large payloads" in goal.knowledge_context

    def test_retrieval_failure_never_blocks_interpretation(self):
        class _BrokenMemory:
            def recommend_for_mission(self, mission_type, tags):
                raise RuntimeError("boom")

        interp = AutonomousInterpreter()
        interp.set_memory_manager(_BrokenMemory())
        goal = interp.interpret("Write a function")
        assert goal.knowledge_context == ""


# ── Project binding fields ───────────────────────────────────────────

class TestProjectBindingFields:
    def test_local_path_and_repository_captured_on_the_goal(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Fix the bug", {
            "local_path": "/home/user/project", "repository": "https://github.com/a/b",
            "branch": "develop",
        })
        assert goal.local_path == "/home/user/project"
        assert goal.repository == "https://github.com/a/b"
        assert goal.branch == "develop"

    def test_absent_by_default(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Fix the bug")
        assert goal.local_path == ""
        assert goal.repository == ""
        assert goal.branch == ""

    def test_repo_url_alias_accepted(self):
        interp = AutonomousInterpreter()
        goal = interp.interpret("Fix the bug", {"repo_url": "https://github.com/a/b"})
        assert goal.repository == "https://github.com/a/b"
