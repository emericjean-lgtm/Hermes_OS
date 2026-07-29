"""Validation Engine for the Intelligent Mission Planner (HOS-042).

Validates mission plans for coherence, completeness, and correctness.
"""

from __future__ import annotations

from backend.mission.planner.planner_models import (
    ComplexityEstimate,
    PlanningResult,
    RuntimeRecommendation,
    TaskBreakdown,
    ValidationReport,
)


class ValidationEngine:
    """Validates mission plans before execution."""

    def validate(self, result: PlanningResult) -> ValidationReport:
        """Run all validation checks on a planning result."""
        report = ValidationReport(total_checks=0)

        self._check_completeness(result, report)
        self._check_dependencies(result, report)
        self._check_resources(result, report)
        self._check_cycles(result, report)
        self._check_orphans(result, report)
        self._check_estimates(result, report)
        self._check_recommendations(result, report)

        report.passed_checks = report.total_checks - report.failed_checks
        report.valid = report.failed_checks == 0

        if not report.valid:
            report.suggestions.append(
                "Review and fix validation issues before starting the mission"
            )

        return report

    def _check_completeness(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check that all planning stages completed."""
        report.total_checks += 1
        required_stages = {
            "decomposing", "building_dependencies",
            "estimating_complexity", "recommending_runtime", "validating",
        }
        completed = {s.value for s in result.stages}
        missing = required_stages - completed

        if missing:
            report.failed_checks += 1
            report.issues.append(f"Missing planning stages: {missing}")

    def _check_dependencies(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check dependency graph integrity."""
        report.total_checks += 1
        task_ids = {t.task_id for t in result.task_breakdowns}

        for task_id, deps in result.dependency_graph.items():
            if task_id not in task_ids:
                report.failed_checks += 1
                report.issues.append(f"Unknown task in dependency graph: '{task_id}'")
                return

            for dep in deps:
                if dep not in task_ids:
                    report.failed_checks += 1
                    report.issues.append(f"Task '{task_id}' depends on unknown task '{dep}'")
                    return

    def _check_resources(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check for resource over-allocation."""
        report.total_checks += 1
        total_vram = sum(
            e.estimated_vram_gb for e in result.complexity_estimates.values()
        )
        total_ram = sum(
            e.estimated_ram_gb for e in result.complexity_estimates.values()
        )

        if total_vram > 48:
            report.warnings.append(
                f"Total VRAM estimate ({total_vram:.1f} GB) is very high — consider splitting tasks"
            )
        if total_ram > 32:
            report.warnings.append(
                f"Total RAM estimate ({total_ram:.1f} GB) is high"
            )

    def _check_cycles(self, result: PlanningResult, report: ValidationReport) -> None:
        """Detect cycles in dependency graph."""
        report.total_checks += 1

        # Build adjacency
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in result.dependency_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in result.dependency_graph:
            if node not in visited:
                if has_cycle(node):
                    report.failed_checks += 1
                    report.issues.append("Dependency graph contains a cycle")
                    return

    def _check_orphans(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check for orphan tasks."""
        report.total_checks += 1
        if len(result.task_breakdowns) <= 1:
            return

        task_ids = {t.task_id for t in result.task_breakdowns}
        has_incoming: set[str] = set()
        for deps in result.dependency_graph.values():
            has_incoming.update(deps)

        # Tasks with no edges at all
        for task in result.task_breakdowns:
            tid = task.task_id
            deps = result.dependency_graph.get(tid, [])
            if not deps and tid not in has_incoming and len(result.task_breakdowns) > 1:
                report.warnings.append(
                    f"Orphan task '{task.title}' — no dependencies and not depended on"
                )

    def _check_estimates(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check complexity estimates."""
        report.total_checks += 1
        for task in result.task_breakdowns:
            est = result.complexity_estimates.get(task.task_id)
            if est is None:
                report.failed_checks += 1
                report.issues.append(f"Missing complexity estimate for '{task.title}'")
                return

    def _check_recommendations(self, result: PlanningResult, report: ValidationReport) -> None:
        """Check runtime recommendations."""
        report.total_checks += 1
        for task in result.task_breakdowns:
            rec = result.runtime_recommendations.get(task.task_id)
            if rec is None:
                report.failed_checks += 1
                report.issues.append(f"Missing runtime recommendation for '{task.title}'")
                return
