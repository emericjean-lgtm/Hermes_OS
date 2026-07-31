"""HOS-018 sentinel tests — Task Planning Engine.

Tests mission-to-graph transformation without any concrete agent.
"""

from __future__ import annotations

import threading

import pytest

from backend.agent.execution_graph import ExecutionGraph
from backend.agent.task_planner import (
    PlannedTask,
    PlanningError,
    PlanningStrategy,
    PlanningValidator,
    TaskMission,
    TaskPlan,
    TaskPlanner,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_task_mission_defaults() -> None:
    m = TaskMission(id="m1", title="Mission")
    assert m.id == "m1"
    assert m.title == "Mission"
    assert m.priority == 5
    assert m.metadata == {}


def test_task_mission_frozen() -> None:
    m = TaskMission(id="m1", title="M")
    with pytest.raises(AttributeError):
        m.id = "m2"  # type: ignore[misc]


def test_planned_task_defaults() -> None:
    t = PlannedTask(id="t1", title="Task")
    assert t.id == "t1"
    assert t.estimated_complexity == 1.0
    assert t.runtime_capability == "chat"
    assert t.dependencies == frozenset()
    assert t.parallelizable is True


def test_task_plan_defaults() -> None:
    mission = TaskMission(id="m1", title="M")
    plan = TaskPlan(mission=mission)
    assert plan.tasks == ()
    assert plan.execution_graph is None
    assert plan.strategy == PlanningStrategy.BALANCED


# ============================================================================
# PlanningStrategy
# ============================================================================


def test_planning_strategy_values() -> None:
    assert PlanningStrategy.SEQUENTIAL.value == "sequential"
    assert PlanningStrategy.BALANCED.value == "balanced"
    assert PlanningStrategy.PARALLEL.value == "parallel"
    assert PlanningStrategy.CONSERVATIVE.value == "conservative"


# ============================================================================
# PlanningValidator
# ============================================================================


def test_validate_tasks_empty() -> None:
    assert PlanningValidator.validate_tasks([]) == []


def test_validate_tasks_duplicate_ids() -> None:
    tasks = [
        PlannedTask(id="t1", title="A"),
        PlannedTask(id="t1", title="B"),
    ]
    errors = PlanningValidator.validate_tasks(tasks)
    assert any("duplicate" in e.lower() for e in errors)


def test_validate_tasks_invalid_complexity() -> None:
    tasks = [PlannedTask(id="t1", title="A", estimated_complexity=15.0)]
    errors = PlanningValidator.validate_tasks(tasks)
    assert any("complexity" in e.lower() for e in errors)


def test_validate_tasks_unknown_dependency() -> None:
    tasks = [PlannedTask(id="t1", title="A", dependencies=frozenset({"nonexistent"}))]
    errors = PlanningValidator.validate_tasks(tasks)
    assert any("unknown" in e.lower() for e in errors)


def test_validate_cycle_among_tasks() -> None:
    tasks = [
        PlannedTask(id="a", title="A", dependencies=frozenset({"b"})),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    errors = PlanningValidator.validate_cycle_among_tasks(tasks)
    assert any("cycle" in e.lower() for e in errors)


def test_validate_cycle_no_cycle() -> None:
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    assert PlanningValidator.validate_cycle_among_tasks(tasks) == []


def test_validate_capabilities_unknown() -> None:
    tasks = [PlannedTask(id="t1", title="A", runtime_capability="nope")]
    errors = PlanningValidator.validate_capabilities(tasks, available_capabilities={"chat"})
    assert any("unknown" in e.lower() for e in errors)


def test_validate_capabilities_known() -> None:
    tasks = [PlannedTask(id="t1", title="A", runtime_capability="chat")]
    assert PlanningValidator.validate_capabilities(tasks, available_capabilities={"chat"}) == []


# ============================================================================
# TaskPlanner: create_plan
# ============================================================================


def test_create_plan_minimal() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Test")
    tasks = [PlannedTask(id="t1", title="Task 1")]
    plan = planner.create_plan(mission, tasks)
    assert plan.mission.id == "m1"
    assert len(plan.tasks) == 1
    assert plan.execution_graph is not None
    assert len(plan.execution_graph.list_nodes()) == 1


def test_create_plan_with_dependencies() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="t1", title="Prepare"),
        PlannedTask(id="t2", title="Build", dependencies=frozenset({"t1"})),
        PlannedTask(id="t3", title="Test", dependencies=frozenset({"t2"})),
    ]
    plan = planner.create_plan(mission, tasks)
    graph = plan.execution_graph
    assert graph is not None
    assert len(graph.list_nodes()) == 3
    assert len(graph.list_edges()) == 2
    # Topological order must respect deps.
    order = graph.topological_sort()
    idx = {n.id: i for i, n in enumerate(order)}
    assert idx["t1"] < idx["t2"]
    assert idx["t2"] < idx["t3"]


def test_create_plan_with_capability_validation() -> None:
    planner = TaskPlanner(available_capabilities={"chat"})
    mission = TaskMission(id="m1", title="Test")
    tasks = [PlannedTask(id="t1", title="A", runtime_capability="unknown")]
    with pytest.raises(PlanningError, match="unknown capability"):
        planner.create_plan(mission, tasks)


# ============================================================================
# Planning strategies
# ============================================================================


def test_sequential_strategy_chains_tasks() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.SEQUENTIAL)
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B"),
        PlannedTask(id="c", title="C"),
    ]
    plan = planner.create_plan(mission, tasks)
    graph = plan.execution_graph
    assert graph is not None
    edges = graph.list_edges()
    assert len(edges) == 2
    assert edges[0].source == "a"
    assert edges[0].target == "b"
    assert edges[1].source == "b"
    assert edges[1].target == "c"


def test_conservative_strategy_adds_all_previous() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.CONSERVATIVE)
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B"),
        PlannedTask(id="c", title="C"),
    ]
    plan = planner.create_plan(mission, tasks)
    graph = plan.execution_graph
    assert graph is not None
    edges = graph.list_edges()
    # a→b, a→c, b→c = 3 edges
    assert len(edges) == 3


def test_parallel_strategy_keeps_declared_deps() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.PARALLEL)
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B"),
        PlannedTask(id="c", title="C"),
    ]
    plan = planner.create_plan(mission, tasks)
    graph = plan.execution_graph
    assert graph is not None
    # No declared dependencies → no edges for PARALLEL.
    assert len(graph.list_edges()) == 0


# ============================================================================
# set_strategy and re-optimisation
# ============================================================================


def test_set_strategy() -> None:
    planner = TaskPlanner()
    assert planner.strategy == PlanningStrategy.BALANCED
    planner.set_strategy(PlanningStrategy.SEQUENTIAL)
    assert planner.strategy == PlanningStrategy.SEQUENTIAL


def test_optimize_plan_applies_new_strategy() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.PARALLEL)
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B"),
    ]
    plan = planner.create_plan(mission, tasks)

    # Re-optimize with sequential.
    planner.set_strategy(PlanningStrategy.SEQUENTIAL)
    opt = planner.optimize_plan(plan)
    assert opt.strategy == PlanningStrategy.SEQUENTIAL
    assert opt.execution_graph is not None
    assert len(opt.execution_graph.list_edges()) == 1  # a→b


# ============================================================================
# Execution graph conversion
# ============================================================================


def test_to_execution_graph() -> None:
    planner = TaskPlanner()
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    graph = planner.to_execution_graph(tasks)
    assert isinstance(graph, ExecutionGraph)
    assert len(graph.list_nodes()) == 2
    assert len(graph.list_edges()) == 1


def test_to_execution_graph_validates() -> None:
    planner = TaskPlanner()
    tasks = [
        PlannedTask(id="a", title="A", dependencies=frozenset({"b"})),
    ]
    with pytest.raises(PlanningError):
        planner.to_execution_graph(tasks)


# ============================================================================
# Plan explanation
# ============================================================================


def test_explain_plan() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.BALANCED)
    mission = TaskMission(id="m1", title="My Mission", objective="Ship it")
    tasks = [
        PlannedTask(id="t1", title="Prepare"),
        PlannedTask(id="t2", title="Build", dependencies=frozenset({"t1"})),
    ]
    plan = planner.create_plan(mission, tasks)
    explanation = planner.explain_plan(plan)
    assert "My Mission" in explanation
    assert "Prepare" in explanation
    assert "balanced" in explanation.lower()


def test_explain_plan_no_graph() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Empty")
    plan = TaskPlan(mission=mission)
    explanation = planner.explain_plan(plan)
    assert "no generated graph" in explanation


# ============================================================================
# Parallel groups
# ============================================================================


def test_parallel_groups_balancing() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.BALANCED)
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A"),
        PlannedTask(id="b", title="B"),
        PlannedTask(id="c", title="C", dependencies=frozenset({"a", "b"})),
    ]
    plan = planner.create_plan(mission, tasks)
    # a and b should be at level 0, c at level 1
    assert len(plan.parallel_groups) >= 2


# ============================================================================
# Estimated duration
# ============================================================================


def test_estimated_duration() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A", estimated_complexity=2.0),
        PlannedTask(id="b", title="B", estimated_complexity=3.0, dependencies=frozenset({"a"})),
        PlannedTask(id="c", title="C", estimated_complexity=1.0, dependencies=frozenset({"a"})),
    ]
    plan = planner.create_plan(mission, tasks)
    # a (level 0) + max(b, c at level 1) = 2 + max(3, 1) = 5
    assert plan.estimated_duration == pytest.approx(5.0)


# ============================================================================
# Validation error propagation
# ============================================================================


def test_create_plan_duplicate_task_ids_raises() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="t1", title="A"),
        PlannedTask(id="t1", title="B"),
    ]
    with pytest.raises(PlanningError, match="Duplicate"):
        planner.create_plan(mission, tasks)


def test_create_plan_cycle_raises() -> None:
    planner = TaskPlanner()
    mission = TaskMission(id="m1", title="Test")
    tasks = [
        PlannedTask(id="a", title="A", dependencies=frozenset({"b"})),
        PlannedTask(id="b", title="B", dependencies=frozenset({"a"})),
    ]
    with pytest.raises(PlanningError, match="Cycle"):
        planner.create_plan(mission, tasks)


# ============================================================================
# Thread safety
# ============================================================================


def test_planner_thread_safety() -> None:
    planner = TaskPlanner(strategy=PlanningStrategy.BALANCED)
    errors: list[Exception] = []

    def create_plan() -> None:
        for i in range(50):
            try:
                mission = TaskMission(id=f"m{i}", title=f"Mission{i}")
                tasks = [PlannedTask(id=f"t{i}", title=f"Task{i}")]
                planner.create_plan(mission, tasks)
            except Exception as e:
                errors.append(e)

    def set_strategy() -> None:
        for _ in range(50):
            planner.set_strategy(
                PlanningStrategy.SEQUENTIAL if _ % 2 == 0 else PlanningStrategy.BALANCED
            )

    t1 = threading.Thread(target=create_plan)
    t2 = threading.Thread(target=set_strategy)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety violations: {errors}"
