"""Mission Planner — core orchestrator for HOS-042.

Transforms user requests into complete, validated mission DAGs
by coordinating all planner components.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionType,
)
from backend.mission.planner.complexity_estimator import ComplexityEstimator
from backend.mission.planner.dependency_builder import DependencyBuilder
from backend.mission.planner.planner_models import (
    PlanningRequest,
    PlanningResult,
    PlanningStage,
    RiskLevel,
)
from backend.mission.planner.runtime_recommender import RuntimeRecommender
from backend.mission.planner.task_decomposer import TaskDecomposer
from backend.mission.planner.template_library import TemplateLibrary
from backend.mission.planner.validation_engine import ValidationEngine


class MissionPlanner:
    """Intelligent mission planner.

    Coordinates task decomposition, dependency building, complexity estimation,
    runtime recommendation, and validation to produce complete mission DAGs.

    Thread-safe. Integrates with GraphExecutor for mission execution.
    """

    def __init__(
        self,
        graph_executor: Optional[GraphExecutor] = None,
        on_event: Optional[Callable] = None,
        decomposer: Optional[TaskDecomposer] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._decomposer = decomposer if decomposer is not None else TaskDecomposer()
        self._dep_builder = DependencyBuilder()
        self._complexity_estimator = ComplexityEstimator()
        self._runtime_recommender = RuntimeRecommender()
        self._validator = ValidationEngine()
        self._templates = TemplateLibrary()
        self._graph_executor = graph_executor
        self._on_event = on_event
        self._results: dict[str, PlanningResult] = {}

    # ── Main Planning Pipeline ───────────────────────────────

    def plan(self, request: PlanningRequest) -> PlanningResult:
        """Execute the full planning pipeline.

        Stages:
        1. Decompose request into tasks
        2. Build dependency graph
        3. Estimate complexity
        4. Recommend runtimes
        5. Validate plan
        """
        result = PlanningResult(request_id=request.request_id)

        try:
            # Stage 1: Decompose
            result.current_stage = PlanningStage.DECOMPOSING
            result.stages.append(PlanningStage.DECOMPOSING)
            breakdowns, method = self._decomposer.decompose_with_method(request)
            result.task_breakdowns = breakdowns
            result.decomposition_method = method
            result.total_nodes = len(breakdowns)
            self._emit("planning.decomposing_completed", {
                "task_count": len(breakdowns), "method": method,
            })

            # Stage 2: Build dependencies
            result.current_stage = PlanningStage.BUILDING_DEPENDENCIES
            result.stages.append(PlanningStage.BUILDING_DEPENDENCIES)
            dep_graph, parallel_groups = self._dep_builder.build_dependencies(breakdowns)
            result.dependency_graph = dep_graph
            result.parallel_groups = parallel_groups
            self._emit("planning.dependencies_built", {
                "nodes": len(breakdowns),
                "parallel_groups": len(parallel_groups),
            })

            # Stage 3: Estimate complexity
            result.current_stage = PlanningStage.ESTIMATING_COMPLEXITY
            result.stages.append(PlanningStage.ESTIMATING_COMPLEXITY)
            estimates = self._complexity_estimator.estimate_all(breakdowns)
            result.complexity_estimates = estimates
            # Compute overall metrics
            result.estimated_total_duration_hours = sum(
                e.estimated_duration_hours for e in estimates.values()
            )
            result.overall_risk = self._compute_overall_risk(estimates)
            self._emit("planning.complexity_estimated", {
                "total_hours": result.estimated_total_duration_hours,
                "risk": result.overall_risk.value,
            })

            # Stage 4: Recommend runtimes
            result.current_stage = PlanningStage.RECOMMENDING_RUNTIME
            result.stages.append(PlanningStage.RECOMMENDING_RUNTIME)
            recommendations = self._runtime_recommender.recommend_all(breakdowns, estimates)
            result.runtime_recommendations = recommendations
            self._emit("planning.runtimes_recommended", {
                "tasks": len(recommendations),
            })

            # Stage 5: Validate
            result.current_stage = PlanningStage.VALIDATING
            result.stages.append(PlanningStage.VALIDATING)
            validation = self._validator.validate(result)
            result.validation = validation
            if not validation.valid:
                result.errors = validation.issues
                result.current_stage = PlanningStage.FAILED
                self._emit("planning.validation_failed", {"issues": validation.issues})
            else:
                result.current_stage = PlanningStage.COMPLETED
                result.stages.append(PlanningStage.COMPLETED)
                result.completed_at = datetime.now(timezone.utc)
                self._emit("planning.completed", {"task_count": result.total_nodes})

        except Exception as exc:
            result.current_stage = PlanningStage.FAILED
            result.errors.append(str(exc))
            self._emit("planning.failed", {"error": str(exc)})

        with self._lock:
            self._results[result.result_id] = result

        return result

    def plan_from_template(
        self,
        template_id: str,
        request: PlanningRequest,
    ) -> PlanningResult:
        """Plan a mission using a predefined template."""
        template = self._templates.get_template(template_id)
        if template is None:
            result = PlanningResult(request_id=request.request_id)
            result.errors.append(f"Template '{template_id}' not found")
            result.current_stage = PlanningStage.FAILED
            return result

        # Use template tasks — an explicit user choice, not a silent
        # fallback, so it gets its own label rather than "llm".
        result = PlanningResult(request_id=request.request_id)
        result.task_breakdowns = list(template.tasks)
        result.decomposition_method = f"template:{template_id}"
        result.total_nodes = len(template.tasks)

        # Run remaining pipeline stages
        dep_graph, parallel_groups = self._dep_builder.build_dependencies(result.task_breakdowns)
        result.dependency_graph = dep_graph
        result.parallel_groups = parallel_groups
        result.stages = [PlanningStage.BUILDING_DEPENDENCIES]

        estimates = self._complexity_estimator.estimate_all(result.task_breakdowns)
        result.complexity_estimates = estimates
        result.estimated_total_duration_hours = sum(e.estimated_duration_hours for e in estimates.values())
        result.overall_risk = self._compute_overall_risk(estimates)
        result.stages.append(PlanningStage.ESTIMATING_COMPLEXITY)

        recommendations = self._runtime_recommender.recommend_all(result.task_breakdowns, estimates)
        result.runtime_recommendations = recommendations
        result.stages.append(PlanningStage.RECOMMENDING_RUNTIME)

        validation = self._validator.validate(result)
        result.validation = validation
        result.stages.append(PlanningStage.VALIDATING)

        if validation.valid:
            result.stages.append(PlanningStage.COMPLETED)
            result.current_stage = PlanningStage.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
        else:
            result.errors = validation.issues
            result.current_stage = PlanningStage.FAILED

        with self._lock:
            self._results[result.result_id] = result

        return result

    # ── Build Mission ────────────────────────────────────────

    def build_mission(
        self,
        result: PlanningResult,
        title: str = "",
        objective: str = "",
    ) -> Mission:
        """Convert a PlanningResult into an executable Mission DAG."""
        mission = Mission(
            title=title or "Planned Mission",
            objective=objective or "Automatically planned mission",
            type=MissionType.DEVELOPMENT,
            priority=self._result_priority(result),
        )
        # Carried onto the mission so a caller inspecting only the mission
        # (report, graph, list) — not the ephemeral PlanningResult — can
        # still tell a real decomposition from the generic-template fallback.
        mission.metadata["decomposition_method"] = result.decomposition_method

        # Build nodes from breakdowns
        nodes: list[MissionNode] = []
        for bd in result.task_breakdowns:
            rec = result.runtime_recommendations.get(bd.task_id)
            est = result.complexity_estimates.get(bd.task_id)
            node = MissionNode(
                node_id=bd.task_id,
                title=bd.title,
                description=bd.description,
                type=bd.category.value,
                priority=MissionPriority(est.suggested_priority if est else "normal"),
                preferred_runtime=rec.model_name if rec else "",
                benchmark_profile=rec.benchmark_profile if rec else "",
                required_skills=bd.required_skills,
                estimated_resources={
                    "vram_gb": est.estimated_vram_gb if est else 0,
                    "ram_gb": est.estimated_ram_gb if est else 0,
                    "tokens": est.estimated_tokens if est else 0,
                },
                estimated_duration_ms=(est.estimated_duration_hours * 3600 * 1000) if est else 0,
                depends_on=bd.depends_on,
                validation_criteria=bd.validation_criteria,
                expected_outputs=bd.expected_outputs,
            )
            nodes.append(node)

        # Build edges from dependency graph
        edges: list[MissionEdge] = []
        for task_id, deps in result.dependency_graph.items():
            for dep_id in deps:
                edges.append(MissionEdge(source_id=dep_id, target_id=task_id))

        # Register with graph executor
        if self._graph_executor:
            issues = self._graph_executor.build_graph(mission, nodes, edges)
            if issues:
                mission.status = result.mission_id  # will have issues

        # `Mission.mission_id` already got a real id from its own
        # default_factory at construction — this used to be overwritten by
        # `result.mission_id` here (always "", since nothing sets it before
        # this point), then copied back onto `result.mission_id` on the next
        # line as a no-op round-trip. Every Autonomous-created mission
        # therefore registered under mission_id="", making it unopenable
        # from `GET /missions/{id}` and unclickable in the Cockpit. Only the
        # real propagation (mission -> result) is needed.
        result.mission_id = mission.mission_id

        return mission

    # ── Query ────────────────────────────────────────────────

    def get_result(self, result_id: str) -> PlanningResult | None:
        with self._lock:
            return self._results.get(result_id)

    def list_results(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "result_id": r.result_id,
                    "request_id": r.request_id,
                    "mission_id": r.mission_id,
                    "stage": r.current_stage.value,
                    "nodes": r.total_nodes,
                    "estimated_hours": r.estimated_total_duration_hours,
                    "risk": r.overall_risk.value,
                    "valid": r.validation.valid if r.validation else False,
                }
                for r in self._results.values()
            ]

    def list_templates(self) -> list[dict]:
        templates = self._templates.list_templates()
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "task_count": len(t.tasks),
                "tags": t.tags,
            }
            for t in templates
        ]

    # ── Helpers ──────────────────────────────────────────────

    def _compute_overall_risk(self, estimates: dict) -> RiskLevel:
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
        max_level = RiskLevel.LOW
        for est in estimates.values():
            if order.get(est.risk_level, 0) > order.get(max_level, 0):
                max_level = est.risk_level
        return max_level

    def _result_priority(self, result: PlanningResult) -> MissionPriority:
        if result.overall_risk == RiskLevel.CRITICAL:
            return MissionPriority.CRITICAL
        elif result.overall_risk == RiskLevel.HIGH:
            return MissionPriority.HIGH
        elif result.overall_risk == RiskLevel.MEDIUM:
            return MissionPriority.NORMAL
        return MissionPriority.BACKGROUND

    def _emit(self, event_type: str, data: dict, severity: str = "info") -> None:
        if self._on_event:
            self._on_event(event_type, data, severity=severity)

    def close(self) -> None:
        """Release the decomposer's Ollama client/bridge, if any.

        Found by the bootstrap's shutdown probe (backend/core/bootstrap/
        bootstrap.py), which calls the first of shutdown/stop/close/flush/
        save/persist a service defines.
        """
        close_fn = getattr(self._decomposer, "close", None)
        if callable(close_fn):
            close_fn()
