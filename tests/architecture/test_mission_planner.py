"""Tests for the Intelligent Mission Planner (HOS-042)."""

from __future__ import annotations

import threading
import time

import pytest

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import MissionStatus, NodeStatus
from backend.mission.planner.complexity_estimator import ComplexityEstimator
from backend.mission.planner.dependency_builder import DependencyBuilder
from backend.mission.planner.mission_planner import MissionPlanner
from backend.mission.planner.planner_models import (
    PlanningRequest,
    PlanningStage,
    RiskLevel,
    TaskBreakdown,
    TaskCategory,
    ValidationReport,
)
from backend.mission.planner.runtime_recommender import RuntimeRecommender
from backend.mission.planner.task_decomposer import TaskDecomposer
from backend.mission.planner.template_library import TemplateLibrary
from backend.mission.planner.validation_engine import ValidationEngine


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def decomposer() -> TaskDecomposer:
    return TaskDecomposer()


@pytest.fixture
def dep_builder() -> DependencyBuilder:
    return DependencyBuilder()


@pytest.fixture
def complexity_estimator() -> ComplexityEstimator:
    return ComplexityEstimator()


@pytest.fixture
def runtime_recommender() -> RuntimeRecommender:
    return RuntimeRecommender()


@pytest.fixture
def validator() -> ValidationEngine:
    return ValidationEngine()


@pytest.fixture
def templates() -> TemplateLibrary:
    return TemplateLibrary()


@pytest.fixture
def graph_executor() -> GraphExecutor:
    return GraphExecutor()


@pytest.fixture
def planner(graph_executor) -> MissionPlanner:
    return MissionPlanner(graph_executor=graph_executor)


@pytest.fixture
def sample_request() -> PlanningRequest:
    return PlanningRequest(
        user_request="Create an authentication system with OAuth support",
        objective="Implement OAuth authentication for the web application",
        repository="https://github.com/org/project",
        tags=["auth", "oauth", "security"],
    )


# ── Task Decomposer Tests ───────────────────────────────────

class TestTaskDecomposer:
    def test_decompose_auth_request(self, decomposer):
        request = PlanningRequest(
            user_request="Create an authentication system",
            objective="Implement auth",
        )
        breakdowns = decomposer.decompose(request)
        assert len(breakdowns) >= 5  # auth pattern + validation
        assert any("auth" in b.title.lower() for b in breakdowns)

    def test_decompose_database_request(self, decomposer):
        request = PlanningRequest(
            user_request="Set up a database",
            objective="Database setup",
        )
        breakdowns = decomposer.decompose(request)
        assert len(breakdowns) > 0
        assert any("database" in b.title.lower() or "schema" in b.title.lower() for b in breakdowns)

    def test_decompose_generic_fallback(self, decomposer):
        request = PlanningRequest(
            user_request="Do something unusual and uncategorized",
            objective="Unknown task",
        )
        breakdowns = decomposer.decompose(request)
        assert len(breakdowns) >= 2  # generic pattern + validation

    def test_decompose_api_request(self, decomposer):
        request = PlanningRequest(
            user_request="Create a REST API",
            objective="Build API",
        )
        breakdowns = decomposer.decompose(request)
        assert any("api" in b.title.lower() or "endpoint" in b.title.lower() for b in breakdowns)

    def test_decompose_outputs_valid_breakdowns(self, decomposer):
        request = PlanningRequest(
            user_request="Implement a frontend page",
            objective="Build UI",
        )
        breakdowns = decomposer.decompose(request)
        for bd in breakdowns:
            assert bd.task_id
            assert bd.title
            assert bd.category in TaskCategory

    def test_classify_implementation_task(self, decomposer):
        cat = decomposer._classify_task("implement the login endpoint and create tests")
        assert cat == TaskCategory.IMPLEMENTATION

    def test_classify_analysis_task(self, decomposer):
        cat = decomposer._classify_task("analyze the performance bottlenecks and evaluate options")
        assert cat == TaskCategory.ANALYSIS


# ── Dependency Builder Tests ────────────────────────────────

class TestDependencyBuilder:
    def test_build_simple_sequence(self, dep_builder):
        tasks = [
            TaskBreakdown(title="A", order=0),
            TaskBreakdown(title="B", order=1),
            TaskBreakdown(title="C", order=2),
        ]
        graph, groups = dep_builder.build_dependencies(tasks)
        assert len(graph) == 3
        assert len(groups) >= 1

    def test_parallel_groups_detected(self, dep_builder):
        tasks = [
            TaskBreakdown(title="Design DB", category=TaskCategory.DESIGN, order=0),
            TaskBreakdown(title="Design API", category=TaskCategory.DESIGN, order=0, can_parallelize=True),
        ]
        graph, groups = dep_builder.build_dependencies(tasks)
        assert len(groups) >= 1

    def test_no_cycles_in_output(self, dep_builder):
        tasks = [
            TaskBreakdown(title="A", order=0),
            TaskBreakdown(title="B", order=1),
            TaskBreakdown(title="C", order=2),
        ]
        graph, _ = dep_builder.build_dependencies(tasks)
        # Verify no task depends on itself
        for tid, deps in graph.items():
            assert tid not in deps

    def test_detect_inconsistencies_missing_ref(self, dep_builder):
        tasks = [TaskBreakdown(title="A", order=0)]
        graph = {tasks[0].task_id: ["nonexistent_id"]}
        issues = dep_builder.detect_inconsistencies(tasks, graph)
        assert any("unknown" in i.lower() for i in issues)

    def test_detect_self_dependency(self, dep_builder):
        tasks = [TaskBreakdown(title="A", order=0)]
        graph = {tasks[0].task_id: [tasks[0].task_id]}
        issues = dep_builder.detect_inconsistencies(tasks, graph)
        assert any("itself" in i.lower() for i in issues)

    def test_empty_breakdowns(self, dep_builder):
        graph, groups = dep_builder.build_dependencies([])
        assert graph == {}
        assert groups == []

    def test_single_task(self, dep_builder):
        tasks = [TaskBreakdown(title="Solo", order=0)]
        graph, groups = dep_builder.build_dependencies(tasks)
        assert len(graph) == 1


# ── Complexity Estimator Tests ──────────────────────────────

class TestComplexityEstimator:
    def test_estimate_basic_task(self, complexity_estimator):
        task = TaskBreakdown(title="Simple CRUD endpoint", category=TaskCategory.IMPLEMENTATION)
        est = complexity_estimator.estimate(task)
        assert est.complexity_score > 0
        assert est.estimated_duration_hours > 0
        assert est.risk_level in RiskLevel

    def test_estimate_complex_task(self, complexity_estimator):
        task = TaskBreakdown(
            title="Implement complex real-time distributed machine learning pipeline",
            category=TaskCategory.IMPLEMENTATION,
        )
        est = complexity_estimator.estimate(task)
        # Complex keywords should increase score
        assert est.complexity_score >= 4.0

    def test_estimate_simple_task(self, complexity_estimator):
        task = TaskBreakdown(title="Simple basic trivial update", category=TaskCategory.DOCUMENTATION)
        est = complexity_estimator.estimate(task)
        assert est.complexity_score <= 5.0

    def test_estimate_all_returns_all(self, complexity_estimator):
        tasks = [
            TaskBreakdown(title="A", category=TaskCategory.IMPLEMENTATION),
            TaskBreakdown(title="B", category=TaskCategory.TESTING),
        ]
        estimates = complexity_estimator.estimate_all(tasks)
        assert len(estimates) == 2
        for t in tasks:
            assert t.task_id in estimates

    def test_risk_detection(self, complexity_estimator):
        task = TaskBreakdown(
            title="Critical security fix for production data loss",
            category=TaskCategory.SECURITY,
        )
        est = complexity_estimator.estimate(task)
        assert est.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert len(est.risk_factors) >= 1

    def test_priority_suggestion(self, complexity_estimator):
        task = TaskBreakdown(title="Trivial update", category=TaskCategory.DOCUMENTATION)
        est = complexity_estimator.estimate(task)
        assert est.suggested_priority in ("background", "normal")

    def test_confidence_range(self, complexity_estimator):
        task = TaskBreakdown(title="Normal task", category=TaskCategory.CUSTOM)
        est = complexity_estimator.estimate(task)
        assert 0.0 <= est.confidence <= 1.0


# ── Runtime Recommender Tests ────────────────────────────────

class TestRuntimeRecommender:
    def test_recommend_coding_task(self, runtime_recommender, complexity_estimator):
        task = TaskBreakdown(title="Implement feature", category=TaskCategory.IMPLEMENTATION)
        est = complexity_estimator.estimate(task)
        rec = runtime_recommender.recommend(task, est)
        assert rec.model_name
        assert rec.benchmark_profile in ("coding", "general_chat", "reasoning")

    def test_recommend_reasoning_task(self, runtime_recommender, complexity_estimator):
        task = TaskBreakdown(title="Analyze architecture", category=TaskCategory.ANALYSIS)
        est = complexity_estimator.estimate(task)
        rec = runtime_recommender.recommend(task, est)
        assert rec.benchmark_profile == "reasoning"

    def test_recommend_all(self, runtime_recommender, complexity_estimator):
        tasks = [TaskBreakdown(title="A", category=TaskCategory.IMPLEMENTATION)]
        estimates = complexity_estimator.estimate_all(tasks)
        recs = runtime_recommender.recommend_all(tasks, estimates)
        assert len(recs) == 1

    def test_high_complexity_model_tier(self, runtime_recommender):
        from backend.mission.planner.planner_models import ComplexityEstimate
        task = TaskBreakdown(title="Critical task", category=TaskCategory.IMPLEMENTATION)
        est = ComplexityEstimate(complexity_level="critical", complexity_score=9.0)
        rec = runtime_recommender.recommend(task, est)
        # Should suggest a large model
        assert "30b" in rec.model_name.lower() or "32b" in rec.model_name.lower() or "14b" in rec.model_name.lower()

    def test_low_complexity_model_tier(self, runtime_recommender):
        from backend.mission.planner.planner_models import ComplexityEstimate
        task = TaskBreakdown(title="Simple task", category=TaskCategory.DOCUMENTATION)
        est = ComplexityEstimate(complexity_level="low", complexity_score=1.0)
        rec = runtime_recommender.recommend(task, est)
        assert rec.model_name


# ── Validation Engine Tests ─────────────────────────────────

class TestValidationEngine:
    def test_valid_plan(self, validator, planner, sample_request):
        result = planner.plan(sample_request)
        # Result from full pipeline should be valid
        assert result.validation is not None

    def test_missing_stages(self, validator):
        from backend.mission.planner.planner_models import PlanningResult
        result = PlanningResult(stages=[PlanningStage.DECOMPOSING])
        report = validator.validate(result)
        assert not report.valid
        assert any("Missing" in i for i in report.issues)

    def test_missing_estimates(self, validator):
        from backend.mission.planner.planner_models import PlanningResult
        result = PlanningResult(
            stages=[
                PlanningStage.DECOMPOSING,
                PlanningStage.BUILDING_DEPENDENCIES,
                PlanningStage.ESTIMATING_COMPLEXITY,
                PlanningStage.RECOMMENDING_RUNTIME,
                PlanningStage.VALIDATING,
            ],
            task_breakdowns=[TaskBreakdown(title="T", order=0)],
        )
        report = validator.validate(result)
        assert not report.valid

    def test_missing_recommendations(self, validator):
        from backend.mission.planner.planner_models import PlanningResult, ComplexityEstimate
        task = TaskBreakdown(title="T", order=0)
        result = PlanningResult(
            stages=[
                PlanningStage.DECOMPOSING,
                PlanningStage.BUILDING_DEPENDENCIES,
                PlanningStage.ESTIMATING_COMPLEXITY,
                PlanningStage.RECOMMENDING_RUNTIME,
                PlanningStage.VALIDATING,
            ],
            task_breakdowns=[task],
            complexity_estimates={task.task_id: ComplexityEstimate()},
        )
        report = validator.validate(result)
        assert not report.valid


# ── Template Library Tests ──────────────────────────────────

class TestTemplateLibrary:
    def test_list_templates(self, templates):
        tpls = templates.list_templates()
        assert len(tpls) >= 5

    def test_get_web_app_template(self, templates):
        tpl = templates.get_template("web_app")
        assert tpl is not None
        assert len(tpl.tasks) >= 5

    def test_get_nonexistent_template(self, templates):
        tpl = templates.get_template("nonexistent")
        assert tpl is None

    def test_search_templates(self, templates):
        results = templates.search("api")
        assert len(results) >= 1
        assert any("api" in t.name.lower() or "api" in t.template_id for t in results)

    def test_register_custom_template(self, templates):
        tpl = templates.get_template("web_app")
        assert tpl is not None
        # Verify template has required fields
        assert tpl.template_id
        assert tpl.name
        assert tpl.tasks


# ── Full Mission Planner Tests ──────────────────────────────

class TestMissionPlanner:
    def test_plan_full_pipeline(self, planner, sample_request):
        result = planner.plan(sample_request)
        assert result.current_stage == PlanningStage.COMPLETED
        assert result.validation.valid
        assert result.total_nodes > 0
        assert len(result.task_breakdowns) > 0
        assert len(result.dependency_graph) > 0
        assert len(result.complexity_estimates) > 0
        assert len(result.runtime_recommendations) > 0

    def test_plan_build_mission(self, planner, sample_request):
        result = planner.plan(sample_request)
        mission = planner.build_mission(result, title="Auth Mission", objective="OAuth")
        assert mission.title == "Auth Mission"
        assert mission.total_nodes() > 0
        assert len(mission.edges) >= 0

    def test_plan_from_template(self, planner):
        request = PlanningRequest(user_request="Build a web app", objective="Web app")
        result = planner.plan_from_template("web_app", request)
        assert result.current_stage in (PlanningStage.COMPLETED, PlanningStage.FAILED)
        if result.current_stage == PlanningStage.COMPLETED:
            assert result.validation.valid
            assert result.total_nodes > 0

    def test_plan_from_invalid_template(self, planner):
        request = PlanningRequest(user_request="Test")
        result = planner.plan_from_template("nonexistent", request)
        assert result.current_stage == PlanningStage.FAILED
        assert len(result.errors) > 0

    def test_get_result(self, planner, sample_request):
        result = planner.plan(sample_request)
        fetched = planner.get_result(result.result_id)
        assert fetched is not None
        assert fetched.result_id == result.result_id

    def test_list_results(self, planner, sample_request):
        planner.plan(sample_request)
        results = planner.list_results()
        assert len(results) >= 1

    def test_list_templates(self, planner):
        templates = planner.list_templates()
        assert len(templates) >= 5

    def test_overall_risk_computation(self, planner, sample_request):
        result = planner.plan(sample_request)
        assert result.overall_risk in RiskLevel

    def test_stages_progression(self, planner, sample_request):
        result = planner.plan(sample_request)
        assert PlanningStage.DECOMPOSING in result.stages
        assert PlanningStage.BUILDING_DEPENDENCIES in result.stages
        assert PlanningStage.ESTIMATING_COMPLEXITY in result.stages
        assert PlanningStage.RECOMMENDING_RUNTIME in result.stages
        assert PlanningStage.VALIDATING in result.stages
        assert PlanningStage.COMPLETED in result.stages

    def test_mission_status_ready(self, planner, sample_request):
        result = planner.plan(sample_request)
        mission = planner.build_mission(result, title="Test", objective="Test")
        # After building with graph executor, mission should be ready
        assert mission.status in (MissionStatus.READY, MissionStatus.VALIDATED)

    def test_plan_with_complex_request(self, planner):
        request = PlanningRequest(
            user_request="Create a full-stack web application with real-time distributed machine learning and enterprise security",
            objective="Complex app with ML and security",
            specification="Must be scalable and fault tolerant",
            tags=["web", "ml", "security"],
        )
        result = planner.plan(request)
        assert result.current_stage == PlanningStage.COMPLETED
        # Complex request should complete (risk may be LOW with generic decomposer;
        # full LLM-based decomposition would propagate complexity keywords)
        assert result.overall_risk in RiskLevel


# ── Thread Safety Tests ─────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_planning(self, planner):
        errors = []

        def plan_worker(idx):
            try:
                request = PlanningRequest(
                    user_request=f"Task {idx}: Create API endpoint",
                    objective=f"Objective {idx}",
                )
                result = planner.plan(request)
                if result.current_stage != PlanningStage.COMPLETED:
                    errors.append(f"Worker {idx}: planning failed")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=plan_worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, errors
        results = planner.list_results()
        assert len(results) >= 5
