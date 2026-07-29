"""Dependency Builder for the Intelligent Mission Planner (HOS-042).

Automatically constructs dependencies between tasks and builds the DAG.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from backend.mission.planner.planner_models import (
    TaskBreakdown,
    TaskCategory,
)


class DependencyBuilder:
    """Builds dependency graphs from task breakdowns.

    Detects sequential, parallel, and synchronization patterns.
    """

    # Tasks that must come after certain categories
    _CATEGORY_ORDER: dict[TaskCategory, int] = {
        TaskCategory.PLANNING: 0,
        TaskCategory.ANALYSIS: 1,
        TaskCategory.DESIGN: 2,
        TaskCategory.IMPLEMENTATION: 3,
        TaskCategory.INTEGRATION: 4,
        TaskCategory.TESTING: 5,
        TaskCategory.SECURITY: 5,
        TaskCategory.OPTIMIZATION: 6,
        TaskCategory.REVIEW: 7,
        TaskCategory.DOCUMENTATION: 8,
        TaskCategory.DEPLOYMENT: 9,
        TaskCategory.CUSTOM: 3,
    }

    def build_dependencies(
        self,
        breakdowns: list[TaskBreakdown],
    ) -> tuple[dict[str, list[str]], list[list[str]]]:
        """Build dependency graph and parallel groups.

        Returns (dependency_graph, parallel_groups)
        - dependency_graph: task_id → [dependency_task_ids]
        - parallel_groups: [[task_ids_that_can_run_in_parallel], ...]
        """
        if not breakdowns:
            return {}, []

        # 1. Apply category ordering (sequential within ordered categories)
        ordered = sorted(breakdowns, key=lambda b: (
            self._CATEGORY_ORDER.get(b.category, 5),
            b.order,
        ))

        # 2. Build dependency graph
        dep_graph: dict[str, list[str]] = {}

        for i, task in enumerate(ordered):
            task_id = task.task_id
            deps: list[str] = list(task.depends_on)  # preserve explicit deps

            # Auto-dependency: tasks depend on previous tasks in same category or earlier
            prev_cat = self._CATEGORY_ORDER.get(task.category, 5)

            for j in range(i):
                earlier = ordered[j]
                earlier_cat = self._CATEGORY_ORDER.get(earlier.category, 5)

                # If same category and can't parallelize, add dependency
                if earlier.category == task.category and not task.can_parallelize:
                    if earlier.task_id not in deps:
                        deps.append(earlier.task_id)
                # If earlier category precedes this one significantly, add dependency
                elif earlier_cat < prev_cat - 1:
                    if earlier.task_id not in deps and task.can_parallelize:
                        pass  # skip — allow parallel across categories
                    elif not task.can_parallelize:
                        if earlier.task_id not in deps:
                            deps.append(earlier.task_id)

            dep_graph[task_id] = deps

        # 3. Build parallel groups
        parallel_groups = self._compute_parallel_groups(ordered, dep_graph)

        return dep_graph, parallel_groups

    def _compute_parallel_groups(
        self,
        tasks: list[TaskBreakdown],
        dep_graph: dict[str, list[str]],
    ) -> list[list[str]]:
        """Compute groups of tasks that can run in parallel."""
        if not tasks:
            return []

        # Build reverse mapping: task_id → blocked tasks
        blocked_by: dict[str, set[str]] = defaultdict(set)
        for task_id, deps in dep_graph.items():
            for dep in deps:
                blocked_by[dep].add(task_id)

        # Find tasks with no dependencies (roots)
        remaining = set(t.task_id for t in tasks)
        completed: set[str] = set()
        groups: list[list[str]] = []

        while remaining:
            # Find tasks whose dependencies are all completed
            ready = [
                tid for tid in remaining
                if all(d in completed for d in dep_graph.get(tid, []))
            ]

            if not ready and remaining:
                # Circular or broken — put remaining in one group
                groups.append(sorted(remaining))
                break

            if ready:
                groups.append(sorted(ready))
                remaining -= set(ready)
                # Don't auto-complete — wait for explicit completion
                # For group computation, we assume all in group complete together
                completed |= set(ready)

        return groups

    def detect_inconsistencies(
        self,
        breakdowns: list[TaskBreakdown],
        dep_graph: dict[str, list[str]],
    ) -> list[str]:
        """Detect inconsistencies in the dependency graph."""
        issues: list[str] = []
        task_ids = {t.task_id for t in breakdowns}

        # Check for missing task references
        for task_id, deps in dep_graph.items():
            for dep in deps:
                if dep not in task_ids:
                    issues.append(f"Task '{task_id}' depends on unknown task '{dep}'")

        # Check for self-dependencies
        for task_id, deps in dep_graph.items():
            if task_id in deps:
                issues.append(f"Task '{task_id}' depends on itself")

        # Check for orphans (no deps and not depended on)
        depended_on: set[str] = set()
        for deps in dep_graph.values():
            depended_on.update(deps)

        for task in breakdowns:
            tid = task.task_id
            if not dep_graph.get(tid) and tid not in depended_on and len(breakdowns) > 1:
                pass  # orphans are fine — they're root tasks

        return issues
