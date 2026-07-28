"""Agent Task Planning Engine (HOS-018).

Transforms a user mission (high-level objective) into a validated
:class:`ExecutionGraph` of :class:`PlannedTask` nodes ready for
execution by the Hermes OS runtime layer.

The planner uses a :class:`PlanningStrategy` to determine the shape
of the graph (sequential, balanced, parallel, conservative).

No concrete agent (Coder, QA, etc.) is imported here.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from backend.agent.execution_graph import (
    AgentEdge,
    AgentNode,
    ExecutionGraph,
    ExecutionGraphValidator,
    NodeType,
    ValidationError,
)


class PlanningStrategy(str, Enum):
    """Strategy that determines the shape of the generated graph.

    * ``SEQUENTIAL`` — each task depends on the previous one (chain).
    * ``BALANCED`` — tasks with no dependencies run in parallel at the
      same level; otherwise respect declared dependencies.
    * ``PARALLEL`` — maximise parallelism: tasks with no declared
      dependencies run in the root level.
    * ``CONSERVATIVE`` — minimise risk: each task depends on its
      predecessor unless explicitly declared independent.
    """

    SEQUENTIAL = "sequential"
    BALANCED = "balanced"
    PARALLEL = "parallel"
    CONSERVATIVE = "conservative"


class PlanningError(Exception):
    """Raised when a planning operation fails."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskMission:
    """An immutable high-level mission.

    Attributes:
        id: Unique mission identifier.
        title: Short mission title.
        description: Extended description.
        objective: Measurable objective statement.
        priority: Mission priority (1 = highest).
        metadata: Free-form payload.
    """

    id: str
    title: str
    description: str = ""
    objective: str = ""
    priority: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedTask:
    """A single task produced by the planner.

    Attributes:
        id: Unique task identifier.
        title: Short title.
        description: Extended description.
        estimated_complexity: Estimated complexity 1-10.
        runtime_capability: Required RAL capability (e.g. ``"chat"``).
        dependencies: Set of task ids this task depends on.
        parallelizable: Whether this task can run in parallel with other
            tasks at the same level.
        metadata: Free-form payload.
    """

    id: str
    title: str
    description: str = ""
    estimated_complexity: float = 1.0
    runtime_capability: str = "chat"
    dependencies: frozenset[str] = frozenset()
    parallelizable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskPlan:
    """The complete output of the task planner.

    Attributes:
        mission: The originating mission.
        tasks: All planned tasks.
        execution_graph: The validated execution graph.
        strategy: The strategy used to produce the plan.
        estimated_duration: Rough estimate based on complexity (arbitrary
            units).
        parallel_groups: Groups of task ids that can run in parallel.
        metadata: Free-form metadata (timestamps, versions, …).
    """

    mission: TaskMission
    tasks: tuple[PlannedTask, ...] = ()
    execution_graph: Optional[ExecutionGraph] = None
    strategy: PlanningStrategy = PlanningStrategy.BALANCED
    estimated_duration: float = 0.0
    parallel_groups: tuple[frozenset[str], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Planning Validator
# ---------------------------------------------------------------------------


class PlanningValidator:
    """Validate tasks and plans before and after graph generation.

    All checks return lists of error messages; an empty list means valid.
    """

    @staticmethod
    def validate_tasks(tasks: list[PlannedTask]) -> list[str]:
        """Validate task consistency: unique ids, dependency references.

        Args:
            tasks: List of tasks to validate.

        Returns:
            A list of error messages (empty = valid).
        """
        errors: list[str] = []
        ids = set()

        for task in tasks:
            if task.id in ids:
                errors.append(f"Duplicate task id '{task.id}'.")
            ids.add(task.id)

            if task.estimated_complexity < 0.0 or task.estimated_complexity > 10.0:
                errors.append(
                    f"Task '{task.id}': estimated_complexity must be 0-10."
                )

            for dep in task.dependencies:
                if dep not in ids:
                    errors.append(
                        f"Task '{task.id}' references unknown dependency '{dep}'."
                    )

        return errors

    @staticmethod
    def validate_cycle_among_tasks(tasks: list[PlannedTask]) -> list[str]:
        """Detect cycles in task dependency declarations.

        Uses the same Kahn's algorithm as the graph validator.
        """
        node_ids = {t.id for t in tasks}
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

        for task in tasks:
            for dep in task.dependencies:
                if dep in adj:
                    adj[dep].append(task.id)
                    in_degree[task.id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            current = queue.pop(0)
            visited += 1
            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(node_ids):
            cycled = [nid for nid, deg in in_degree.items() if deg > 0]
            return [f"Cycle detected among tasks: {cycled}"]
        return []

    @staticmethod
    def validate_capabilities(
        tasks: list[PlannedTask],
        available_capabilities: Optional[set[str]] = None,
    ) -> list[str]:
        """Check that all tasks reference known capabilities.

        Args:
            tasks: Tasks to check.
            available_capabilities: Set of known capability names. If
                ``None``, capability checking is skipped.

        Returns:
            An error list (empty = valid).
        """
        if available_capabilities is None:
            return []
        errors: list[str] = []
        for task in tasks:
            if task.runtime_capability not in available_capabilities:
                errors.append(
                    f"Task '{task.id}' requires unknown capability "
                    f"'{task.runtime_capability}'."
                )
        return errors

    @staticmethod
    def validate_plan(
        tasks: list[PlannedTask],
        *,
        available_capabilities: Optional[set[str]] = None,
    ) -> list[str]:
        """Run all validation checks on a task list.

        Returns:
            Combined error list (empty = valid).
        """
        errors: list[str] = []
        errors.extend(PlanningValidator.validate_tasks(tasks))
        errors.extend(PlanningValidator.validate_cycle_among_tasks(tasks))
        errors.extend(
            PlanningValidator.validate_capabilities(tasks, available_capabilities)
        )
        return errors


# ---------------------------------------------------------------------------
# Task Planner
# ---------------------------------------------------------------------------


class TaskPlanner:
    """Transform a :class:`TaskMission` into a validated :class:`TaskPlan`.

    The planner is thread-safe and strategy-aware.

    Args:
        strategy: The planning strategy to use.
        available_capabilities: Optional set of known RAL capabilities
            for validation.
    """

    def __init__(
        self,
        strategy: PlanningStrategy = PlanningStrategy.BALANCED,
        *,
        available_capabilities: Optional[set[str]] = None,
    ) -> None:
        self._strategy = strategy
        self._available_capabilities = available_capabilities
        self._lock = threading.Lock()

    @property
    def strategy(self) -> PlanningStrategy:
        """Return the current strategy."""
        return self._strategy

    def set_strategy(self, strategy: PlanningStrategy) -> None:
        """Change the planning strategy.

        Args:
            strategy: New strategy.
        """
        with self._lock:
            self._strategy = strategy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_plan(
        self,
        mission: TaskMission,
        tasks: list[PlannedTask],
    ) -> TaskPlan:
        """Create a complete :class:`TaskPlan` from a mission and tasks.

        The tasks are validated, enriched, and converted to an
        :class:`ExecutionGraph`.

        Args:
            mission: The originating mission.
            tasks: The list of planned tasks.

        Returns:
            A validated :class:`TaskPlan`.

        Raises:
            PlanningError: If validation fails.
        """
        with self._lock:
            # Validate.
            errors = PlanningValidator.validate_plan(
                tasks, available_capabilities=self._available_capabilities,
            )
            if errors:
                raise PlanningError("; ".join(errors))

            # Optimise according to strategy.
            optimised = self._apply_strategy(tasks)

            # Build the execution graph.
            graph = self._tasks_to_graph(optimised, strategy=self._strategy)

            # Compute parallel groups from graph plan.
            g_plan = graph.generate_plan()
            parallel_groups = g_plan.levels

            # Estimate duration.
            duration = self._estimate_duration(optimised, g_plan)

            plan = TaskPlan(
                mission=mission,
                tasks=tuple(optimised),
                execution_graph=graph,
                strategy=self._strategy,
                estimated_duration=duration,
                parallel_groups=parallel_groups,
                metadata={
                    "created_at": time.time(),
                    "strategy": self._strategy.value,
                    "task_count": len(optimised),
                },
            )
            return plan

    def validate_plan(
        self,
        mission: TaskMission,
        tasks: list[PlannedTask],
    ) -> list[str]:
        """Validate tasks without creating a plan.

        Returns:
            Error list (empty = valid).
        """
        return PlanningValidator.validate_plan(
            tasks, available_capabilities=self._available_capabilities,
        )

    def optimize_plan(
        self,
        plan: TaskPlan,
    ) -> TaskPlan:
        """Re-create a plan with the current strategy for re-optimisation.

        Args:
            plan: An existing plan.

        Returns:
            A re-optimised plan.
        """
        return self.create_plan(plan.mission, list(plan.tasks))

    def to_execution_graph(
        self,
        tasks: list[PlannedTask],
    ) -> ExecutionGraph:
        """Convert a list of tasks directly into an :class:`ExecutionGraph`.

        This is a lower-level method that skips mission wrapping and
        returns only the graph.

        Args:
            tasks: Planned tasks to convert.

        Returns:
            A validated execution graph.

        Raises:
            PlanningError: If validation fails.
        """
        errors = PlanningValidator.validate_plan(
            tasks, available_capabilities=self._available_capabilities,
        )
        if errors:
            raise PlanningError("; ".join(errors))
        return self._tasks_to_graph(tasks, strategy=self._strategy)

    def explain_plan(self, plan: TaskPlan) -> str:
        """Produce a human-readable explanation of the plan.

        Args:
            plan: A completed plan.

        Returns:
            A multi-line explanation string.
        """
        graph = plan.execution_graph
        if graph is None:
            return f"Plan for '{plan.mission.title}' has no generated graph."

        roots = graph.get_roots()
        leaves = graph.get_leaves()

        lines: list[str] = []
        lines.append(f"Mission: {plan.mission.title}")
        lines.append(f"Strategy: {plan.strategy.value}")
        lines.append(f"Total tasks: {len(plan.tasks)}")
        lines.append(f"Estimated duration: {plan.estimated_duration:.1f} units")
        lines.append(f"Parallel groups: {len(plan.parallel_groups)}")
        lines.append(f"Root task(s): {[n.id for n in roots]}")
        lines.append(f"Leaf task(s): {[n.id for n in leaves]}")
        lines.append("")

        # List tasks by level.
        for i, group in enumerate(plan.parallel_groups):
            lines.append(f"  Level {i}: {', '.join(sorted(group))}")

        lines.append("")
        lines.append("Task details:")
        task_map = {t.id: t for t in plan.tasks}
        for task in plan.tasks:
            dep_str = ", ".join(sorted(task.dependencies)) if task.dependencies else "none"
            lines.append(
                f"  - {task.id} [{task.runtime_capability}]: "
                f"'{task.title}' (deps: {dep_str}, "
                f"complexity: {task.estimated_complexity:.1f})"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_strategy(
        self,
        tasks: list[PlannedTask],
    ) -> list[PlannedTask]:
        """Adjust dependencies according to the current strategy."""
        if self._strategy == PlanningStrategy.SEQUENTIAL:
            return self._make_sequential(tasks)
        if self._strategy == PlanningStrategy.CONSERVATIVE:
            return self._make_conservative(tasks)
        # BALANCED and PARALLEL keep declared dependencies as-is.
        return tasks

    @staticmethod
    def _make_sequential(tasks: list[PlannedTask]) -> list[PlannedTask]:
        """Chain all tasks in insertion order."""
        updated: list[PlannedTask] = []
        for i, task in enumerate(tasks):
            deps: set[str] = set()
            if i > 0:
                deps.add(tasks[i - 1].id)
            updated.append(PlannedTask(
                id=task.id,
                title=task.title,
                description=task.description,
                estimated_complexity=task.estimated_complexity,
                runtime_capability=task.runtime_capability,
                dependencies=frozenset(deps),
                parallelizable=task.parallelizable,
                metadata=task.metadata,
            ))
        return updated

    @staticmethod
    def _make_conservative(tasks: list[PlannedTask]) -> list[PlannedTask]:
        """Each task depends on all previous tasks *not already declared*."""
        updated: list[PlannedTask] = []
        all_previous: set[str] = set()
        for i, task in enumerate(tasks):
            merged = set(task.dependencies) | all_previous
            # Remove self if present.
            merged.discard(task.id)
            updated.append(PlannedTask(
                id=task.id,
                title=task.title,
                description=task.description,
                estimated_complexity=task.estimated_complexity,
                runtime_capability=task.runtime_capability,
                dependencies=frozenset(merged),
                parallelizable=task.parallelizable,
                metadata=task.metadata,
            ))
            all_previous.add(task.id)
        return updated

    @staticmethod
    def _tasks_to_graph(
        tasks: list[PlannedTask],
        strategy: PlanningStrategy,
    ) -> ExecutionGraph:
        """Build a validated ExecutionGraph from PlannedTask list."""
        graph = ExecutionGraph()

        # Create AgentNode for each PlannedTask.
        for task in tasks:
            ntype = NodeType.PARALLEL if task.parallelizable else NodeType.TASK
            graph.add_node(AgentNode(
                id=task.id,
                name=task.title[:200],
                type=ntype,
                runtime_capability=task.runtime_capability,
                metadata={
                    "description": task.description,
                    "estimated_complexity": task.estimated_complexity,
                    "original_deps": sorted(task.dependencies),
                },
            ))

        # Create edges for each declared dependency.
        for task in tasks:
            for dep in task.dependencies:
                try:
                    graph.add_edge(AgentEdge(source=dep, target=task.id))
                except Exception:
                    # Edge will be rejected if dependency is invalid;
                    # validation should catch this, but we keep going
                    # to report all issues.
                    pass

        return graph

    @staticmethod
    def _estimate_duration(
        tasks: list[PlannedTask],
        g_plan: Any,
    ) -> float:
        """Estimate total duration based on complexity and parallelism."""
        # Sum complexity of the critical path (longest chain).
        if not g_plan.levels:
            return sum(t.estimated_complexity for t in tasks)

        # Each level contributes its maximum-complexity task.
        total = 0.0
        seen: set[str] = set()
        for level in g_plan.levels:
            max_c = 0.0
            for nid in level:
                if nid not in seen:
                    seen.add(nid)
                for t in tasks:
                    if t.id == nid:
                        max_c = max(max_c, t.estimated_complexity)
                        break
            total += max_c

        return total
