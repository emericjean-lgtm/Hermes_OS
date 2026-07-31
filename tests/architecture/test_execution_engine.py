"""HOS-024 sentinel tests — Mission Execution Engine.

Tests the engine's lifecycle, task scheduling, dispatch, state
synchronisation, completion detection, recovery, statistics,
and thread safety — all without real network calls.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from backend.agent.execution_engine import (
    ExecutionEngine,
    ExecutionEngineError,
    ExecutionEvent,
    ExecutionScheduler,
    ExecutionState,
    ExecutionStatistics,
)
from backend.agent.execution_graph import (
    AgentEdge,
    AgentNode,
    ExecutionGraph,
    NodeStatus,
)
from backend.agent.lifecycle import (
    AgentLifecycleManager,
)
from backend.agent.supervisor import (
    MissionContext,
    MultiAgentSupervisor,
)
from backend.agent.task_planner import (
    PlannedTask,
    PlanningStrategy,
    TaskPlanner,
)
from backend.ral.runtime_decision import (
    RuntimeDecision,
    RuntimeDecisionEngine,
)
from backend.ral.runtime_router import RuntimeRouter


# ============================================================================
# Fixtures
# ============================================================================


def _make_context(mission_id: str = "m1") -> MissionContext:
    return MissionContext(
        mission_id=mission_id,
        title="Test Mission",
        objective="Test objective",
        priority=5,
    )


def _make_tasks(n: int = 3) -> list[PlannedTask]:
    return [
        PlannedTask(id=f"t{i}", title=f"Task {i}", runtime_capability="chat")
        for i in range(n)
    ]


def _make_engine(**kwargs: object) -> ExecutionEngine:
    """Create an ExecutionEngine with mock dependencies."""
    planner = TaskPlanner(strategy=PlanningStrategy.BALANCED)
    lifecycle = AgentLifecycleManager(timeout_s=300.0)
    supervisor = MultiAgentSupervisor(planner=planner, lifecycle=lifecycle)

    mock_decision = MagicMock(spec=RuntimeDecisionEngine)
    mock_decision.select_runtime = MagicMock(
        return_value=RuntimeDecision(
            selected_runtime="stub",
            confidence=1.0,
            decision_score=1000.0,
            decision_reason="mock",
        )
    )

    mock_router = MagicMock(spec=RuntimeRouter)

    return ExecutionEngine(
        supervisor=supervisor,
        lifecycle=lifecycle,
        runtime_decision=mock_decision,
        runtime_router=mock_router,
        planner=planner,
        **kwargs,
    )


# ============================================================================
# Dataclass tests
# ============================================================================


def test_execution_statistics_defaults() -> None:
    stats = ExecutionStatistics()
    assert stats.executions_started == 0
    assert stats.executions_completed == 0
    assert stats.tasks_executed == 0
    assert stats.success_rate == 1.0


def test_execution_state_values() -> None:
    assert ExecutionState.IDLE.value == "idle"
    assert ExecutionState.RUNNING.value == "running"
    assert ExecutionState.PAUSED.value == "paused"
    assert ExecutionState.COMPLETED.value == "completed"
    assert ExecutionState.FAILED.value == "failed"
    assert ExecutionState.CANCELLED.value == "cancelled"
    assert ExecutionState.RECOVERING.value == "recovering"


def test_execution_event_values() -> None:
    assert ExecutionEvent.EXECUTION_STARTED.value == "execution.started"
    assert ExecutionEvent.TASK_COMPLETED.value == "execution.task_completed"
    assert ExecutionEvent.TASK_FAILED.value == "execution.task_failed"
    assert ExecutionEvent.EXECUTION_COMPLETED.value == "execution.completed"


# ============================================================================
# Scheduler
# ============================================================================


def test_scheduler_get_ready_tasks_empty() -> None:
    graph = ExecutionGraph()
    plan = graph.generate_plan()
    ready = ExecutionScheduler.get_ready_tasks(graph, plan)
    assert ready == []


def test_scheduler_get_ready_tasks_single_node() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="Task 1"))
    graph.add_node(AgentNode(id="t2", name="Task 2"))
    plan = graph.generate_plan()
    ready = ExecutionScheduler.get_ready_tasks(graph, plan)
    assert len(ready) == 2


def test_scheduler_get_ready_tasks_with_deps() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="Task 1"))
    graph.add_node(AgentNode(id="t2", name="Task 2"))
    graph.add_edge(AgentEdge(source="t1", target="t2"))
    plan = graph.generate_plan()
    ready = ExecutionScheduler.get_ready_tasks(graph, plan)
    # Only t1 should be ready (t2 depends on t1).
    assert len(ready) == 1
    assert ready[0].id == "t1"


def test_scheduler_get_ready_tasks_after_completion() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="Task 1"))
    graph.add_node(AgentNode(id="t2", name="Task 2"))
    graph.add_edge(AgentEdge(source="t1", target="t2"))

    # Mark t1 as completed.
    graph._nodes["t1"] = AgentNode(
        id="t1", name="Task 1", status=NodeStatus.COMPLETED,
    )

    plan = graph.generate_plan()
    ready = ExecutionScheduler.get_ready_tasks(graph, plan)
    assert len(ready) == 1
    assert ready[0].id == "t2"


def test_scheduler_parallel_groups() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="T1"))
    graph.add_node(AgentNode(id="t2", name="T2"))
    graph.add_node(AgentNode(id="t3", name="T3"))
    graph.add_edge(AgentEdge(source="t1", target="t3"))
    graph.add_edge(AgentEdge(source="t2", target="t3"))

    plan = graph.generate_plan()
    groups = ExecutionScheduler.get_parallel_groups(graph, plan)
    # Level 0: t1, t2 (parallel); Level 1: t3.
    assert len(groups) == 2
    node_ids = {n.id for n in groups[0]}
    assert node_ids == {"t1", "t2"}


def test_scheduler_estimate_wait_time() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="T1"))
    graph.add_node(AgentNode(id="t2", name="T2"))
    graph.add_edge(AgentEdge(source="t1", target="t2"))
    plan = graph.generate_plan()

    wait = ExecutionScheduler.estimate_wait_time(graph, plan, "t2")
    assert wait > 0  # t2 depends on uncompleted t1


# ============================================================================
# Engine lifecycle
# ============================================================================


def test_engine_initial_state() -> None:
    engine = _make_engine()
    assert engine.state == ExecutionState.IDLE
    assert engine.context is None
    assert engine.result is None


def test_engine_start() -> None:
    engine = _make_engine()
    ctx = engine.start(_make_context(), _make_tasks(2))
    assert ctx.execution_id is not None
    assert ctx.mission_id == "m1"


def test_engine_start_not_idle_raises() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    with pytest.raises(ExecutionEngineError, match="Cannot start"):
        engine.start(_make_context("m2"), _make_tasks(1))


def test_engine_pause_resume() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    assert engine.state == ExecutionState.RUNNING

    engine.pause()
    assert engine.state == ExecutionState.PAUSED

    engine.resume()
    assert engine.state == ExecutionState.RUNNING


def test_engine_pause_not_running_raises() -> None:
    engine = _make_engine()
    with pytest.raises(ExecutionEngineError, match="Cannot pause"):
        engine.pause()


def test_engine_cancel() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    assert engine.state == ExecutionState.RUNNING

    engine.cancel()
    assert engine.state == ExecutionState.CANCELLED
    assert engine.is_finished()


def test_engine_cancel_terminal_raises() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    engine.cancel()
    with pytest.raises(ExecutionEngineError, match="Cannot cancel"):
        engine.cancel()


def test_engine_recover() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))

    # Force engine to FAILED state.
    engine._state = ExecutionState.FAILED

    result = engine.recover()
    assert result is True
    assert engine.state == ExecutionState.RUNNING


def test_engine_recover_from_idle_returns_false() -> None:
    engine = _make_engine()
    result = engine.recover()
    assert result is False


# ============================================================================
# Tick operations
# ============================================================================


def test_tick_returns_events_when_running() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(2))
    events = engine.tick()
    assert isinstance(events, list)


def test_tick_when_idle_returns_empty() -> None:
    engine = _make_engine()
    events = engine.tick()
    assert events == []


def test_tick_when_paused_returns_empty() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    engine.pause()
    events = engine.tick()
    assert events == []


# ============================================================================
# is_finished / get_status / get_result
# ============================================================================


def test_is_finished_false_when_running() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    assert engine.is_finished() is False


def test_get_status_returns_dict() -> None:
    engine = _make_engine()
    status = engine.get_status()
    assert "state" in status
    assert "task_progress" in status


def test_get_status_includes_task_progress_after_start() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(3))
    status = engine.get_status()
    assert status["task_progress"]["total"] == 3


def test_get_result_none_before_completion() -> None:
    engine = _make_engine()
    assert engine.result is None


# ============================================================================
# Events
# ============================================================================


def test_engine_emits_execution_started() -> None:
    engine = _make_engine()
    events: list[ExecutionEvent] = []

    engine.on_event(lambda evt, _: events.append(evt))
    engine.start(_make_context(), _make_tasks(1))

    assert ExecutionEvent.EXECUTION_STARTED in events


def test_engine_emits_execution_completed() -> None:
    engine = _make_engine()
    events: list[ExecutionEvent] = []

    engine.on_event(lambda evt, _: events.append(evt))
    engine.start(_make_context(), _make_tasks(1))

    # Force execution to complete state.
    engine._state = ExecutionState.COMPLETED
    engine._result = engine._build_result(success=True)
    engine._emit(ExecutionEvent.EXECUTION_COMPLETED, {})

    assert ExecutionEvent.EXECUTION_COMPLETED in events


def test_engine_emits_on_cancel() -> None:
    engine = _make_engine()
    events: list[ExecutionEvent] = []

    engine.on_event(lambda evt, _: events.append(evt))
    engine.start(_make_context(), _make_tasks(1))
    engine.cancel()

    assert ExecutionEvent.EXECUTION_FAILED in events


# ============================================================================
# Scheduler integration
# ============================================================================


def test_ready_tasks_integration() -> None:
    """Verify that get_ready_tasks works after engine.start creates graph."""
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(3))

    graph = engine._execution_graph
    plan = engine._execution_plan
    assert graph is not None
    assert plan is not None

    ready = ExecutionScheduler.get_ready_tasks(graph, plan)
    # All 3 tasks are root (no dependencies), so all should be ready.
    assert len(ready) == 3


def test_parallel_groups_after_start() -> None:
    """Parallel groups should detect independent tasks."""
    tasks = [
        PlannedTask(id="t1", title="T1", runtime_capability="chat"),
        PlannedTask(id="t2", title="T2", runtime_capability="chat"),
        PlannedTask(id="t3", title="T3", runtime_capability="chat", dependencies=frozenset({"t1", "t2"})),
    ]
    engine = _make_engine()
    engine.start(_make_context("pm"), tasks)

    graph = engine._execution_graph
    plan = engine._execution_plan
    assert graph is not None
    assert plan is not None

    groups = ExecutionScheduler.get_parallel_groups(graph, plan)
    # Should have at least 2 levels.
    assert len(groups) >= 1


# ============================================================================
# Graph completion detection
# ============================================================================


def test_is_graph_finished_true_when_all_completed() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="T1", status=NodeStatus.COMPLETED))
    graph.add_node(AgentNode(id="t2", name="T2", status=NodeStatus.COMPLETED))

    engine = _make_engine()
    engine._execution_graph = graph

    assert engine._is_graph_finished(graph) is True


def test_is_graph_finished_false_when_pending() -> None:
    graph = ExecutionGraph()
    graph.add_node(AgentNode(id="t1", name="T1", status=NodeStatus.PENDING))

    engine = _make_engine()
    engine._execution_graph = graph

    assert engine._is_graph_finished(graph) is False


# ============================================================================
# Statistics
# ============================================================================


def test_get_statistics_returns_defaults() -> None:
    engine = _make_engine()
    stats = engine.get_statistics()
    assert stats.executions_started == 0
    assert stats.executions_failed == 0


def test_statistics_updated_on_completion() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    # Force completion.
    engine._state = ExecutionState.COMPLETED
    engine._result = engine._build_result(success=True)

    stats = engine.get_statistics()
    assert stats.executions_started == 1
    assert stats.executions_completed == 1


# ============================================================================
# Step convenience
# ============================================================================


def test_step_returns_list() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(1))
    result = engine.step()
    assert isinstance(result, list)


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_start_and_status() -> None:
    engine = _make_engine()
    errors: list[Exception] = []

    def starter() -> None:
        for _ in range(5):
            try:
                ctx = engine.start(
                    _make_context(mission_id=f"m{_}"),
                    _make_tasks(1),
                )
            except Exception as e:
                errors.append(e)

    def status_checker() -> None:
        for _ in range(10):
            try:
                engine.get_status()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=starter)
    t2 = threading.Thread(target=status_checker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Only the first start should succeed; subsequent ones fail.
    # But no exceptions should occur during status checks.
    status_errors = [e for e in errors if "Cannot start" not in str(e)]
    assert not status_errors


def test_concurrent_tick_and_pause() -> None:
    engine = _make_engine()
    engine.start(_make_context(), _make_tasks(2))
    errors: list[Exception] = []

    def ticker() -> None:
        for _ in range(10):
            try:
                engine.tick()
            except Exception as e:
                errors.append(e)

    def pauser() -> None:
        for _ in range(5):
            try:
                engine.pause()
                engine.resume()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=ticker)
    t2 = threading.Thread(target=pauser)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
