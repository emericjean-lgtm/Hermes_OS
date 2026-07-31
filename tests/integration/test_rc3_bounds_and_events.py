"""RC3 regression tests — retention bounds and mission event delivery.

These lock in two classes of defect found in the RC3 audit:

* Six collections on the execution path grew for the lifetime of the process.
  Because ``get_progress()``, ``is_all_done()`` and ``stats()`` each walk their
  registry once per task, unbounded growth turned them into O(missions-run) and
  throughput decayed from 983 to 256 missions/s over a 3600-mission run.
* ``MissionExecutor`` accepted an ``on_event`` dispatcher, stored it, and never
  called it, so no mission lifecycle event ever reached a subscriber.

The bounds are asserted against the classes' own published constants rather than
hard-coded numbers, so retuning a cap does not break the tests — only removing
one does.
"""

from __future__ import annotations

import time

import pytest

from backend.autonomous.autonomous_memory_loop import AutonomousMemoryLoop
from backend.autonomous.autonomous_models import AutonomousReport
from backend.autonomous.autonomous_orchestrator import AutonomousOrchestrator
from backend.autonomous.decision_engine import DecisionEngine
from backend.execution.agent_coordinator import AgentCoordinator
from backend.execution.execution_models import (
    TaskExecution,
    TaskExecutionStatus,
    ValidationOutcome,
)
from backend.execution.mission_executor import MissionExecutor
from backend.execution.task_executor import RealTaskExecutor
from backend.execution.task_scheduler import TaskScheduler
from backend.execution.validation_engine import ValidationEngine
from tests.support.fake_inference import fake_chat


# ── Retention bounds ──────────────────────────────────────────────────────


def test_scheduler_registry_is_bounded():
    sched = TaskScheduler()
    over = sched.MAX_RETAINED_TASKS * 2
    for i in range(over):
        task = TaskExecution(task_id=f"t{i}", title="t")
        task.status = TaskExecutionStatus.COMPLETED
        sched.register_task(task, [f"t{i - 1}"])

    assert len(sched._tasks) <= sched.MAX_RETAINED_TASKS
    # Dependencies must be pruned with their task, or they become the new leak.
    assert len(sched._dependencies) <= sched.MAX_RETAINED_TASKS


def test_scheduler_bound_holds_even_when_nothing_is_terminal():
    """Eviction prefers finished work but must never let the cap be exceeded."""
    sched = TaskScheduler()
    for i in range(sched.MAX_RETAINED_TASKS + 200):
        sched.register_task(TaskExecution(task_id=f"p{i}", title="p"))

    assert len(sched._tasks) <= sched.MAX_RETAINED_TASKS


def test_scheduler_progress_matches_a_full_scan():
    """get_progress()/is_all_done() must stay exact under direct status writes.

    Callers assign ``task.status`` themselves as well as going through
    update_task(), and a retried task returns from a terminal state to PENDING,
    so any maintained tally would drift. This walks a task set through both.
    """
    sched = TaskScheduler()
    tasks = [TaskExecution(task_id=f"t{i}", title="t") for i in range(40)]
    for task in tasks:
        sched.register_task(task)

    terminal = {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED,
                TaskExecutionStatus.FAILED}
    walk = [TaskExecutionStatus.RUNNING, TaskExecutionStatus.COMPLETED,
            TaskExecutionStatus.PENDING, TaskExecutionStatus.FAILED,
            TaskExecutionStatus.SKIPPED]

    for step in range(120):
        tasks[step % len(tasks)].status = walk[step % len(walk)]

        live = list(sched._tasks.values())
        expected_completed = sum(
            1 for t in live
            if t.status in {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED}
        )
        progress = sched.get_progress()
        assert progress["total"] == len(live)
        assert progress["completed"] == expected_completed
        assert progress["failed"] == sum(
            1 for t in live if t.status == TaskExecutionStatus.FAILED)
        assert progress["running"] == sum(
            1 for t in live if t.status == TaskExecutionStatus.RUNNING)
        assert sched.is_all_done() == all(t.status in terminal for t in live)


def test_scheduler_get_task_is_a_lookup_not_a_scan():
    sched = TaskScheduler()
    for i in range(sched.MAX_RETAINED_TASKS):
        sched.register_task(TaskExecution(task_id=f"t{i}", title="t"))

    assert sched.get_task("t0") is not None or sched.get_task(
        f"t{sched.MAX_RETAINED_TASKS - 1}") is not None
    assert sched.get_task("nope") is None

    target = f"t{sched.MAX_RETAINED_TASKS - 1}"
    started = time.perf_counter()
    for _ in range(20_000):
        sched.get_task(target)
    per_call_us = (time.perf_counter() - started) / 20_000 * 1e6
    # A linear scan of a full registry costs orders of magnitude more than this;
    # the threshold is loose enough not to be a machine-speed test.
    assert per_call_us < 50, f"get_task took {per_call_us:.1f}us/call — scanning?"


def test_mission_executor_event_tail_is_bounded():
    executor = MissionExecutor(task_executor=RealTaskExecutor(chat=fake_chat))
    for i in range(executor.MAX_RETAINED_EVENTS + 500):
        executor._publish("execution.started", {"execution_id": f"e{i}"})

    assert len(executor._events) == executor.MAX_RETAINED_EVENTS
    # A ring buffer keeps the newest, not the oldest.
    assert executor.get_events()[-1]["execution_id"] == \
        f"e{executor.MAX_RETAINED_EVENTS + 499}"


def test_decision_engine_history_is_bounded():
    engine = DecisionEngine()
    for i in range(engine.MAX_RETAINED_DECISIONS + 300):
        engine.select_agent(f"task_type_{i}", {})

    assert engine.stats()["total_decisions"] == engine.MAX_RETAINED_DECISIONS
    # get_decisions() must still slice correctly off a deque.
    assert len(engine.get_decisions(limit=10)) == 10
    assert engine.get_decisions(limit=0) == []


def test_validation_engine_state_is_bounded():
    engine = ValidationEngine()
    for i in range(engine.MAX_RETAINED_VALIDATIONS + 200):
        task = TaskExecution(task_id=f"t{i}", title="t")
        task.result = {"ok": True}
        engine.set_criteria(task.task_id, ["result_present"])
        assert engine.validate(task) in tuple(ValidationOutcome)

    assert len(engine._results) <= engine.MAX_RETAINED_VALIDATIONS
    assert len(engine._criteria) <= engine.MAX_RETAINED_VALIDATIONS
    assert len(engine._history) <= engine.MAX_RETAINED_VALIDATIONS


def test_agent_coordinator_assignments_are_bounded():
    coordinator = AgentCoordinator()
    coordinator.register_agent("a1", ["analysis"])
    for i in range(coordinator.MAX_RETAINED_ASSIGNMENTS + 200):
        coordinator.assign(TaskExecution(task_id=f"t{i}", title="t"))

    assert len(coordinator._assignments) <= coordinator.MAX_RETAINED_ASSIGNMENTS


def test_memory_loop_learnings_are_bounded():
    loop = AutonomousMemoryLoop()
    for i in range(loop.MAX_RETAINED_LEARNINGS + 100):
        loop.process_report(AutonomousReport(goal_id=f"g{i}", success=True))

    assert len(loop._learnings) == loop.MAX_RETAINED_LEARNINGS
    assert len(loop.get_learnings(limit=5)) == 5
    assert loop.get_learnings(limit=0) == []
    assert loop.get_learning_summary()["missions"] == loop.MAX_RETAINED_LEARNINGS


def test_orchestrator_goal_retention_is_bounded():
    executor = RealTaskExecutor(chat=fake_chat)
    try:
        orch = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor))
        for i in range(orch.MAX_RETAINED_GOALS + 120):
            orch.start_goal(f"bounded goal {i}")

        assert len(orch._goals) <= orch.MAX_RETAINED_GOALS
        assert len(orch._sessions) <= orch.MAX_RETAINED_GOALS
        # The goal→session index must be evicted alongside, or it is the leak.
        assert len(orch._session_by_goal) <= orch.MAX_RETAINED_GOALS
    finally:
        executor.close()


# ── Event delivery ────────────────────────────────────────────────────────


@pytest.fixture
def captured_events():
    seen: list[tuple[str, dict]] = []
    yield seen


def test_mission_lifecycle_events_reach_the_dispatcher(captured_events):
    """Every event the mission executor records must also be dispatched.

    ``on_event`` was accepted and never invoked, so `execution.started`,
    `execution.planning`, `execution.task_started` and `execution.completed`
    were recorded privately and never delivered — the Cockpit's live feed could
    not see a mission begin or end.
    """
    def dispatch(topic, payload=None, **_):
        captured_events.append((topic, payload or {}))

    executor = RealTaskExecutor(chat=fake_chat, on_event=dispatch)
    try:
        orch = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor,
                                             on_event=dispatch))
        goal = orch.start_goal("Analyse the authentication module")
        assert goal.status.value == "completed"
    finally:
        executor.close()

    delivered = [topic for topic, _ in captured_events]
    for expected in ("execution.started", "execution.planning",
                     "execution.task_started", "execution.completed"):
        assert expected in delivered, f"{expected} never reached a subscriber"


def test_task_completion_is_announced_exactly_once(captured_events):
    """Two layers used to publish execution.task_completed for the same task."""
    def dispatch(topic, payload=None, **_):
        captured_events.append((topic, payload or {}))

    executor = RealTaskExecutor(chat=fake_chat, on_event=dispatch)
    try:
        orch = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor,
                                             on_event=dispatch))
        orch.start_goal("Analyse the authentication module")
    finally:
        executor.close()

    completions = [t for t, _ in captured_events if t == "execution.task_completed"]
    assert len(completions) == 1, (
        f"task completion announced {len(completions)}x — subscribers double-count")


def test_a_failing_dispatcher_cannot_fail_the_mission():
    """Telemetry must never break the work it describes."""
    def exploding(topic, payload=None, **_):
        raise RuntimeError("subscriber is down")

    executor = RealTaskExecutor(chat=fake_chat)
    try:
        orch = AutonomousOrchestrator(
            mission_executor=MissionExecutor(task_executor=executor,
                                             on_event=exploding))
        goal = orch.start_goal("Analyse the authentication module")
        assert goal.status.value == "completed"
    finally:
        executor.close()
