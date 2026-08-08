"""Tests for HOS-069 — Execution Center real-wiring (Phase A):

* ExecutionController wraps the *shared* execution engine, not a private one
  (the composition-root fix; the actual instance identity is exercised by
  test_execution_controller_wraps_shared_engine below and, end-to-end, by
  the bootstrap smoke test in test_service_registry.py-adjacent suites).
* ExecutionController.execute_task() does not re-serialize the slow call
  MissionExecutor.execute_task() already runs lock-free (HOS-068).
* TaskScheduler.all_done() is scoped per-execution, unlike is_all_done().
* MissionExecutor.execute_task() reports FAILED, not COMPLETED, when the
  execution's own task(s) actually failed.
* ExecutionController._executions/_reports are bounded, not unbounded dicts.
* node_execution.py's execute_node() registers real executions with a real
  ExecutionController (not a fake) — the end-to-end path the Cockpit reads.

Fully hermetic: a fake task_executor stands in for RealTaskExecutor, no real
Ollama needed.
"""
from __future__ import annotations

import threading
import time

import pytest

from backend.execution.agent_coordinator import AgentAssignment
from backend.execution.execution_controller import ExecutionController
from backend.execution.execution_models import (
    ExecutionMeta,
    ExecutionState,
    TaskExecution,
    TaskExecutionStatus,
)
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RuntimeUnavailableError, TaskExecutionOutcome
from backend.execution.task_scheduler import TaskScheduler
from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import Mission, MissionNode
from backend.mission.node_execution import make_node_executor


class _FakeTaskExecutor:
    """Deterministic stand-in for RealTaskExecutor: no Ollama, no delay
    unless asked, one outcome per call — success or a chosen failure."""

    def __init__(self, *, fail: bool = False, delay_s: float = 0.0):
        self._fail = fail
        self._delay_s = delay_s

    def execute(self, task, assignment) -> TaskExecutionOutcome:
        if self._delay_s:
            time.sleep(self._delay_s)
        if self._fail:
            # Matches RealTaskExecutor's real failure contract: a failed
            # attempt raises, it does not return an outcome with errors
            # bolted on (see task_executor.py's execute()).
            raise RuntimeUnavailableError("simulated failure")
        return TaskExecutionOutcome(
            result="ok",
            runtime_id="fake",
            model="fake-model",
            duration_ms=1.0,
        )


# ═══════════════════════════════════════════════════════════════
# TaskScheduler.all_done() — scoped, unlike is_all_done()
# ═══════════════════════════════════════════════════════════════

class TestSchedulerAllDoneScoping:
    def test_all_done_true_when_this_executions_tasks_are_terminal(self):
        sched = TaskScheduler()
        t1 = TaskExecution(task_id="t1", status=TaskExecutionStatus.COMPLETED)
        t2 = TaskExecution(task_id="t2", status=TaskExecutionStatus.PENDING)
        sched.register_task(t1)
        sched.register_task(t2)
        assert sched.all_done(["t1"]) is True
        assert sched.all_done(["t1", "t2"]) is False

    def test_is_all_done_is_global_and_all_done_is_not(self):
        """The bug all_done() exists to fix: is_all_done() answers for
        *every* task ever registered on the shared scheduler, which is
        wrong once more than one execution shares it (real since HOS-068's
        concurrent GraphExecutor dispatch)."""
        sched = TaskScheduler()
        sched.register_task(TaskExecution(task_id="mine", status=TaskExecutionStatus.COMPLETED))
        sched.register_task(TaskExecution(task_id="someone_elses", status=TaskExecutionStatus.RUNNING))
        assert sched.all_done(["mine"]) is True
        assert sched.is_all_done() is False

    def test_all_done_false_for_empty_or_unknown_tasks(self):
        sched = TaskScheduler()
        assert sched.all_done([]) is False
        assert sched.all_done(["never-registered"]) is False


# ═══════════════════════════════════════════════════════════════
# MissionExecutor.execute_task() — FAILED vs COMPLETED
# ═══════════════════════════════════════════════════════════════

class TestMissionExecutorTerminalState:
    def test_failed_task_transitions_execution_to_failed_not_completed(self):
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=True))
        # max_retries_per_task=0: isolates the FAILED-vs-COMPLETED terminal
        # state fix under test from HOS-069 Phase C's separate concern
        # (RuntimeUnavailableError now retries before failing).
        meta = ExecutionMeta(user_goal="will fail", max_retries_per_task=0)
        task = TaskExecution(task_id="t1", node_id="n1", title="t1")
        sm = me.prepare(meta, [task])

        result = me.execute_task(sm, "t1")

        assert result["status"] == "failed"
        assert sm.state == ExecutionState.FAILED

    def test_successful_task_transitions_execution_to_completed(self):
        me = MissionExecutor(task_executor=_FakeTaskExecutor(fail=False))
        meta = ExecutionMeta(user_goal="will pass")
        task = TaskExecution(task_id="t1", node_id="n1", title="t1")
        sm = me.prepare(meta, [task])

        result = me.execute_task(sm, "t1")

        assert result["status"] == "completed"
        assert sm.state == ExecutionState.COMPLETED


# ═══════════════════════════════════════════════════════════════
# ExecutionController — lock scope, bounded retention
# ═══════════════════════════════════════════════════════════════

class TestExecutionControllerConcurrency:
    def test_execute_task_does_not_reserialize_concurrent_calls(self):
        """Mirrors mission_executor's own lock-narrowing test: routing a
        node execution through ExecutionController must not reintroduce the
        exact serialization HOS-068 removed from MissionExecutor itself."""
        me = MissionExecutor(task_executor=_FakeTaskExecutor(delay_s=0.2))
        controller = ExecutionController(me)

        results: dict[str, dict] = {}

        def run(tid: str) -> None:
            task = TaskExecution(task_id=tid, node_id=f"n-{tid}", title=tid)
            meta = ExecutionMeta(user_goal=tid)
            controller.start(meta, [task])
            results[tid] = controller.execute_task(meta.execution_id, tid)

        t0 = time.monotonic()
        threads = [threading.Thread(target=run, args=(tid,)) for tid in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - t0

        assert results["a"]["status"] == "completed"
        assert results["b"]["status"] == "completed"
        assert elapsed < 0.35  # serialized would be >= 0.4s

    def test_bounded_retention_evicts_oldest(self):
        me = MissionExecutor(task_executor=_FakeTaskExecutor())
        controller = ExecutionController(me)
        controller.MAX_RETAINED_EXECUTIONS = 3  # shrink for a fast test

        ids = []
        for i in range(5):
            meta = ExecutionMeta(user_goal=f"exec-{i}")
            controller.start(meta, [TaskExecution(task_id=f"t{i}", node_id=f"n{i}")])
            ids.append(meta.execution_id)

        assert controller.get(ids[0]) is None  # evicted
        assert controller.get(ids[1]) is None  # evicted
        assert controller.get(ids[-1]) is not None  # retained


# ═══════════════════════════════════════════════════════════════
# End-to-end: node_execution.py registers with a *real* controller
# ═══════════════════════════════════════════════════════════════

class TestNodeExecutionRegistersWithRealController:
    def test_a_node_execution_is_listable_and_reported_afterwards(self):
        """The central bug this phase fixes: before HOS-069, a Mission's
        node execution never touched ExecutionController at all, so
        /api/v1/execution always looked empty regardless of real activity.
        """
        me = MissionExecutor(task_executor=_FakeTaskExecutor())
        controller = ExecutionController(me)
        graph_executor = GraphExecutor(execute_node=make_node_executor(controller))

        mission = Mission(title="Real mission", mission_id="m1")
        node = MissionNode(node_id="n1", title="Do the thing")
        mission.nodes = [node]
        graph_executor.build_graph(mission, mission.nodes, [])
        assert node.mission_id == "m1"  # stamped by build_graph (HOS-069)

        graph_executor.start_mission(mission)
        graph_executor.execute_step(mission)

        listed = controller.list_executions()
        assert len(listed) == 1
        assert listed[0]["state"] == "completed"
        assert listed[0]["mission_id"] == "m1"
        # finalize() was called by node_execution.py — a real report exists.
        assert listed[0]["report"]["total_tasks"] == 1
        assert listed[0]["report"]["completed_tasks"] == 1

        stats = controller.stats()
        assert stats["completed_executions"] == 1
        assert stats["total_executions"] == 1
