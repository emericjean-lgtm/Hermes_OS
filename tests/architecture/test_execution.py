"""Tests for HOS-050 — Autonomous Mission Execution Engine."""

from __future__ import annotations

import threading
import time
import pytest

from backend.execution.execution_models import (
    ExecutionMeta,
    ExecutionPriority,
    ExecutionState,
    ExecutionTimeline,
    TaskExecution,
    TaskExecutionStatus,
    ValidationOutcome,
    CheckpointType,
    SchedulerStrategy,
)
from backend.execution.execution_state import ExecutionStateMachine
from backend.execution.task_scheduler import TaskScheduler, SchedulePlan
from backend.execution.agent_coordinator import AgentCoordinator, AgentAssignment
from backend.execution.validation_engine import ValidationEngine
from backend.execution.feedback_loop import FeedbackLoop, ExecutionReport
from backend.execution.optimization_engine import OptimizationEngine
from backend.execution.mission_executor import MissionExecutor
from backend.execution.execution_controller import ExecutionController


# ── Helpers ──────────────────────────────────────────────────

def make_task(task_id: str = "t1", title: str = "Test task") -> TaskExecution:
    return TaskExecution(task_id=task_id, node_id=f"node-{task_id}", title=title)


def make_meta(goal: str = "Test mission") -> ExecutionMeta:
    return ExecutionMeta(user_goal=goal)


# ═══════════════════════════════════════════════════════════════
# ExecutionStateMachine
# ═══════════════════════════════════════════════════════════════

class TestExecutionStateMachine:
    def test_initial_state(self):
        sm = ExecutionStateMachine()
        assert sm.state == ExecutionState.CREATED

    def test_valid_transition(self):
        sm = ExecutionStateMachine()
        sm.transition(ExecutionState.PLANNING)
        assert sm.state == ExecutionState.PLANNING

    def test_invalid_transition_raises(self):
        sm = ExecutionStateMachine()
        with pytest.raises(ValueError):
            sm.transition(ExecutionState.RUNNING)  # CREATED → RUNNING invalid

    def test_full_lifecycle(self):
        sm = ExecutionStateMachine()
        transitions = [
            ExecutionState.PLANNING,
            ExecutionState.READY,
            ExecutionState.RUNNING,
            ExecutionState.VALIDATING,
            ExecutionState.COMPLETED,
        ]
        for target in transitions:
            sm.transition(target)
        assert sm.state == ExecutionState.COMPLETED
        assert sm.is_terminal()
        assert len(sm.history) == 5

    def test_pause_resume(self):
        sm = ExecutionStateMachine()
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)
        sm.transition(ExecutionState.PAUSED)
        assert sm.state == ExecutionState.PAUSED
        sm.transition(ExecutionState.RUNNING)
        assert sm.state == ExecutionState.RUNNING

    def test_waiting_approval(self):
        sm = ExecutionStateMachine()
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)
        sm.transition(ExecutionState.WAITING_APPROVAL)
        assert sm.state == ExecutionState.WAITING_APPROVAL
        sm.transition(ExecutionState.RUNNING)
        assert sm.state == ExecutionState.RUNNING

    def test_retry_from_failed(self):
        sm = ExecutionStateMachine()
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)
        sm.transition(ExecutionState.FAILED)
        assert sm.state == ExecutionState.FAILED
        sm.transition(ExecutionState.RUNNING)  # retry
        assert sm.state == ExecutionState.RUNNING

    def test_cancel(self):
        sm = ExecutionStateMachine()
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.CANCELLED)
        assert sm.state == ExecutionState.CANCELLED
        assert sm.is_terminal()

    def test_save_and_get_checkpoint(self):
        sm = ExecutionStateMachine(make_meta())
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)
        cp = sm.save_checkpoint(CheckpointType.PAUSE, {"task_id": "t1"})
        assert cp is not None
        got = sm.get_checkpoint(cp.checkpoint_id)
        assert got is not None
        assert got.checkpoint_id == cp.checkpoint_id
        assert got.state == ExecutionState.RUNNING

    def test_get_last_checkpoint(self):
        sm = ExecutionStateMachine(make_meta())
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.save_checkpoint(CheckpointType.AUTO)
        sm.transition(ExecutionState.RUNNING)
        cp2 = sm.save_checkpoint(CheckpointType.PAUSE)
        last = sm.get_last_checkpoint()
        assert last is not None
        assert last.checkpoint_id == cp2.checkpoint_id

    def test_stats(self):
        sm = ExecutionStateMachine(make_meta())
        sm.transition(ExecutionState.PLANNING)
        s = sm.stats()
        assert s["state"] == "planning"
        assert s["history_length"] == 1

    def test_is_active(self):
        sm = ExecutionStateMachine()
        assert not sm.is_active()
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)
        assert sm.is_active()


# ═══════════════════════════════════════════════════════════════
# TaskScheduler
# ═══════════════════════════════════════════════════════════════

class TestTaskScheduler:
    def test_register_and_get_ready(self):
        ts = TaskScheduler()
        t1 = make_task("t1", "First")
        t2 = make_task("t2", "Second")
        ts.register_task(t1)
        ts.register_task(t2)
        ready = ts.get_ready_tasks()
        assert len(ready) == 2

    def test_dependencies_block(self):
        ts = TaskScheduler()
        t1 = make_task("t1", "Dep task")
        t2 = make_task("t2", "Depends on t1")
        ts.register_task(t1)
        ts.register_task(t2, ["t1"])
        ready = ts.get_ready_tasks()
        assert ready == ["t1"]  # Only t1 ready, t2 blocked

    def test_dependency_satisfied_after_completion(self):
        ts = TaskScheduler()
        t1 = make_task("t1", "Dependency")
        t2 = make_task("t2", "Waits on t1")
        ts.register_task(t1)
        ts.register_task(t2, ["t1"])
        ts.update_task("t1", TaskExecutionStatus.COMPLETED)
        ready = ts.get_ready_tasks()
        assert "t2" in ready

    def test_blocked_tasks(self):
        ts = TaskScheduler()
        t1 = make_task("t1", "Blocked task")
        ts.register_task(t1, ["nonexistent"])
        blocked = ts.get_blocked_tasks()
        assert "t1" in blocked

    def test_build_plan(self):
        ts = TaskScheduler()
        t1 = make_task("t1", "Step 1")
        t2 = make_task("t2", "Step 2")
        t3 = make_task("t3", "Step 3")
        ts.register_task(t1)
        ts.register_task(t2, ["t1"])
        ts.register_task(t3, ["t1"])
        plan = ts.build_plan()
        assert len(plan.waves) >= 2  # t1 in wave0, t2+t3 in wave1
        assert plan.total_tasks == 3

    def test_get_progress(self):
        ts = TaskScheduler()
        ts.register_task(make_task("t1"))
        ts.register_task(make_task("t2"))
        ts.update_task("t1", TaskExecutionStatus.COMPLETED)
        p = ts.get_progress()
        assert p["total"] == 2
        assert p["completed"] == 1
        assert p["percent"] == 50.0

    def test_is_all_done(self):
        ts = TaskScheduler()
        ts.register_task(make_task("t1"))
        ts.update_task("t1", TaskExecutionStatus.COMPLETED)
        assert ts.is_all_done()

    def test_empty_scheduler(self):
        ts = TaskScheduler()
        assert ts.is_all_done()
        assert ts.get_ready_tasks() == []


# ═══════════════════════════════════════════════════════════════
# AgentCoordinator
# ═══════════════════════════════════════════════════════════════

class TestAgentCoordinator:
    def test_register_and_assign(self):
        ac = AgentCoordinator()
        ac.register_agent("coder", ["coding", "python", "backend"])
        task = make_task("t1", "Code a backend API")
        assignment = ac.assign(task)
        assert assignment.agent_id == "coder"
        assert assignment.task_id == "t1"
        assert assignment.confidence > 0

    def test_agent_load_tracking(self):
        ac = AgentCoordinator()
        ac.register_agent("coder", ["coding"])
        ac.assign(make_task("t1", "Code API"))
        assert ac.get_agent_load("coder") == 1
        ac.assign(make_task("t2", "Code DB"))
        assert ac.get_agent_load("coder") == 2
        ac.release_agent("t1")
        assert ac.get_agent_load("coder") == 1

    def test_runtime_selection(self):
        ac = AgentCoordinator()
        ac.register_runtime("ollama", {"type": "local", "model": "qwen3"})
        ac.register_agent("coder", ["coding"], preferred_runtime="ollama")
        assignment = ac.assign(make_task("t1", "Write code"))
        assert assignment.runtime_id == "ollama"

    def test_skill_selection(self):
        ac = AgentCoordinator()
        ac.register_skill("python-coding", {"description": "Python coding", "domain": "backend"})
        ac.register_skill("react-ui", {"description": "React UI", "domain": "frontend"})
        ac.register_agent("coder", ["coding"])
        assignment = ac.assign(make_task("t1", "Write Python backend code"))
        assert "python-coding" in assignment.skill_ids
        assert "react-ui" not in assignment.skill_ids

    def test_fallback_agent(self):
        ac = AgentCoordinator()
        assignment = ac.assign(make_task("t1", "Random task"))
        assert assignment.agent_id in {"default"} or assignment.agent_id != ""

    def test_get_assignment(self):
        ac = AgentCoordinator()
        ac.register_agent("coder", ["coding"])
        ac.assign(make_task("t1", "Code"))
        a = ac.get_assignment("t1")
        assert a is not None
        assert a.agent_id == "coder"

    def test_stats(self):
        ac = AgentCoordinator()
        ac.register_agent("coder", ["coding"])
        s = ac.stats()
        assert s["agents_registered"] == 1


# ═══════════════════════════════════════════════════════════════
# ValidationEngine
# ═══════════════════════════════════════════════════════════════

class TestValidationEngine:
    def test_pass_validation(self):
        ve = ValidationEngine()
        task = make_task("t1", "Test")
        task.result = "success result"
        outcome = ve.validate(task)
        assert outcome == ValidationOutcome.PASS

    def test_fail_on_no_result(self):
        ve = ValidationEngine()
        task = make_task("t1", "Test")
        task.result = None
        ve.set_criteria("t1", ["result_present"])
        outcome = ve.validate(task)
        assert outcome == ValidationOutcome.FAIL

    def test_fail_on_errors(self):
        ve = ValidationEngine()
        task = make_task("t1", "Test")
        task.result = "partial"
        task.errors = ["error occurred"]
        ve.set_criteria("t1", ["no_errors"])
        outcome = ve.validate(task)
        assert outcome == ValidationOutcome.FAIL

    def test_needs_review(self):
        ve = ValidationEngine()
        task = make_task("t1", "Test")
        task.result = "result"
        ve.set_criteria("t1", ["needs_human_review"])
        outcome = ve.validate(task)
        assert outcome == ValidationOutcome.NEEDS_REVIEW

    def test_no_result_no_errors(self):
        ve = ValidationEngine()
        task = make_task("t1", "Test")
        task.result = "partial result"
        task.errors = []
        ve.set_criteria("t1", ["needs_human_review"])
        outcome = ve.validate(task)
        assert outcome == ValidationOutcome.NEEDS_REVIEW

    def test_stats(self):
        ve = ValidationEngine()
        task = make_task("t1")
        task.result = "ok"
        ve.validate(task)
        s = ve.stats()
        assert s["total_validated"] == 1


# ═══════════════════════════════════════════════════════════════
# FeedbackLoop
# ═══════════════════════════════════════════════════════════════

class TestFeedbackLoop:
    def test_analyze_success(self):
        fl = FeedbackLoop()
        report = ExecutionReport(
            execution_id="e1",
            mission_id="m1",
            state=ExecutionState.COMPLETED,
            total_tasks=5,
            completed_tasks=5,
        )
        result = fl.analyze(report)
        assert result["state"] == "completed"
        assert result["efficiency"] == 100.0
        assert len(result["learnings"]) >= 1

    def test_analyze_failure(self):
        fl = FeedbackLoop()
        report = ExecutionReport(
            execution_id="e2",
            mission_id="m2",
            state=ExecutionState.FAILED,
            total_tasks=5,
            completed_tasks=2,
            failed_tasks=3,
            errors=["timeout"],
        )
        result = fl.analyze(report)
        assert result["efficiency"] < 100.0

    def test_get_memory_input(self):
        fl = FeedbackLoop()
        report = ExecutionReport(execution_id="e3", mission_id="m3", state=ExecutionState.COMPLETED)
        fl.analyze(report)
        mem = fl.get_memory_input("e3")
        assert mem["mission_id"] == "m3"

    def test_get_intelligence_input(self):
        fl = FeedbackLoop()
        report = ExecutionReport(execution_id="e4", mission_id="m4", state=ExecutionState.COMPLETED)
        fl.analyze(report)
        intel = fl.get_intelligence_input("e4")
        assert intel["state"] == "completed"

    def test_stats(self):
        fl = FeedbackLoop()
        report = ExecutionReport(execution_id="e5", mission_id="m5", state=ExecutionState.COMPLETED)
        fl.analyze(report)
        s = fl.stats()
        assert s["reports_analyzed"] == 1


# ═══════════════════════════════════════════════════════════════
# OptimizationEngine
# ═══════════════════════════════════════════════════════════════

class TestOptimizationEngine:
    def test_record_and_identify_slow(self):
        oe = OptimizationEngine()
        oe.record_execution("e1", {
            "task_name": "slow-task",
            "duration_ms": 5000,
            "expected_ms": 1000,
            "duration_ratio": 5.0,
        })
        slow = oe.identify_slow_tasks()
        assert len(slow) == 1
        assert slow[0]["task"] == "slow-task"

    def test_identify_runtime_issues(self):
        oe = OptimizationEngine()
        oe.record_execution("e1", {"runtime_id": "bad-rt", "duration_ms": 20000})
        oe.record_execution("e2", {"runtime_id": "bad-rt", "duration_ms": 15000})
        issues = oe.identify_runtime_issues()
        assert len(issues) == 1
        assert issues[0]["runtime_id"] == "bad-rt"

    def test_generate_recommendations(self):
        oe = OptimizationEngine()
        oe.record_execution("e1", {
            "task_name": "slow", "duration_ms": 5000, "expected_ms": 1000, "duration_ratio": 5.0,
            "runtime_id": "bad-rt",
        })
        oe.record_execution("e2", {"runtime_id": "bad-rt", "duration_ms": 20000})
        recs = oe.generate_recommendations()
        assert len(recs) >= 1

    def test_stats(self):
        oe = OptimizationEngine()
        oe.record_execution("e1", {"duration_ms": 100})
        s = oe.stats()
        assert s["observations"] == 1


# ═══════════════════════════════════════════════════════════════
# MissionExecutor
# ═══════════════════════════════════════════════════════════════

class TestMissionExecutor:
    def test_prepare_and_execute(self):
        me = MissionExecutor()
        meta = make_meta("Build a web app")
        tasks = [make_task("t1", "Plan architecture"), make_task("t2", "Code backend")]
        sm = me.prepare(meta, tasks)
        assert sm.state == ExecutionState.READY

    def test_execute_single_task(self):
        me = MissionExecutor()
        meta = make_meta("Build API")
        tasks = [make_task("t1", "Create endpoint")]
        sm = me.prepare(meta, tasks)
        result = me.execute_task(sm, "t1")
        assert result["task_id"] == "t1"
        assert result["status"] in {"completed", "failed"}

    def test_execute_task_not_found(self):
        me = MissionExecutor()
        meta = make_meta()
        sm = me.prepare(meta, [])
        result = me.execute_task(sm, "nonexistent")
        assert result["status"] == "not_found"

    def test_finalize(self):
        me = MissionExecutor()
        meta = make_meta("Build web app")
        tasks = [make_task("t1", "Step 1")]
        sm = me.prepare(meta, tasks)
        me.execute_task(sm, "t1")
        report = me.finalize(sm)
        assert report.execution_id == meta.execution_id
        assert report.total_tasks == 1

    def test_pause_resume(self):
        me = MissionExecutor()
        meta = make_meta()
        sm = me.prepare(meta, [make_task("t1")])
        sm.transition(ExecutionState.RUNNING)
        assert me.pause(sm)
        assert sm.state == ExecutionState.PAUSED
        assert me.resume(sm)
        assert sm.state == ExecutionState.RUNNING

    def test_cancel(self):
        me = MissionExecutor()
        meta = make_meta()
        sm = me.prepare(meta, [make_task("t1")])
        assert me.cancel(sm)
        assert sm.state == ExecutionState.CANCELLED

    def test_get_timeline(self):
        me = MissionExecutor()
        meta = make_meta("Test timeline")
        sm = me.prepare(meta, [make_task("t1")])
        tl = me.get_timeline(sm)
        assert tl["state"] == "ready"
        assert len(tl["history"]) >= 1

    def test_get_events(self):
        me = MissionExecutor()
        meta = make_meta()
        sm = me.prepare(meta, [make_task("t1")])
        events = me.get_events()
        assert len(events) >= 2  # execution.started + execution.planning

    def test_stats(self):
        me = MissionExecutor()
        meta = make_meta()
        me.prepare(meta, [make_task("t1")])
        s = me.stats()
        assert "scheduler" in s
        assert "events_published" in s
        assert s["events_published"] >= 2


# ═══════════════════════════════════════════════════════════════
# ExecutionController
# ═══════════════════════════════════════════════════════════════

class TestExecutionController:
    def test_start_and_get(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta("Build API")
        sm = ec.start(meta, [make_task("t1", "Design schema")])
        info = ec.get(meta.execution_id)
        assert info is not None
        assert info["state"] == "ready"

    def test_execute_task(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta("Build API")
        ec.start(meta, [make_task("t1", "Design")])
        result = ec.execute_task(meta.execution_id, "t1")
        assert result["task_id"] == "t1"

    def test_pause_resume(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta()
        ec.start(meta, [make_task("t1")])
        # Transition to RUNNING first
        sm = ec._executions[meta.execution_id]
        sm.transition(ExecutionState.RUNNING)
        assert ec.pause(meta.execution_id)
        assert ec.resume(meta.execution_id)

    def test_cancel(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta()
        ec.start(meta, [make_task("t1")])
        assert ec.cancel(meta.execution_id)

    def test_finalize(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta("Build API")
        ec.start(meta, [make_task("t1", "Step 1")])
        ec.execute_task(meta.execution_id, "t1")
        report = ec.finalize(meta.execution_id)
        assert report.execution_id == meta.execution_id

    def test_get_timeline(self):
        ec = ExecutionController(MissionExecutor())
        meta = make_meta("Build API")
        ec.start(meta, [make_task("t1")])
        tl = ec.get_timeline(meta.execution_id)
        assert tl is not None
        assert "state" in tl

    def test_list_executions(self):
        ec = ExecutionController(MissionExecutor())
        ec.start(make_meta("Mission 1"), [make_task("t1")])
        ec.start(make_meta("Mission 2"), [make_task("t2")])
        lst = ec.list_executions()
        assert len(lst) == 2

    def test_stats(self):
        ec = ExecutionController(MissionExecutor())
        ec.start(make_meta("M1"), [make_task("t1")])
        s = ec.stats()
        assert s["total_executions"] == 1


# ═══════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════

class TestRoutes:
    def test_start_execution(self):
        from backend.execution.routes import start_execution, _reset_controller
        _reset_controller()
        result = start_execution(
            goal="Build a web app",
            tasks=[
                {"id": "t1", "title": "Plan architecture"},
                {"id": "t2", "title": "Code backend"},
            ],
            mission_id="m1",
        )
        assert result["state"] == "ready"
        assert result["tasks_registered"] == 2

    def test_start_with_dependencies(self):
        from backend.execution.routes import start_execution, _reset_controller
        _reset_controller()
        result = start_execution(
            goal="Build API",
            tasks=[
                {"id": "t1", "title": "Design schema"},
                {"id": "t2", "title": "Implement endpoints"},
            ],
            dependencies={"t2": ["t1"]},
        )
        assert result["tasks_registered"] == 2

    def test_get_execution(self):
        from backend.execution.routes import start_execution, get_execution, _reset_controller
        _reset_controller()
        result = start_execution("Test", [{"id": "t1", "title": "Test"}])
        info = get_execution(result["execution_id"])
        assert info is not None
        assert info["state"] == "ready"

    def test_get_execution_not_found(self):
        from backend.execution.routes import get_execution, _reset_controller
        _reset_controller()
        info = get_execution("nonexistent")
        assert "error" in info

    def test_list_executions(self):
        from backend.execution.routes import start_execution, list_executions, _reset_controller
        _reset_controller()
        start_execution("M1", [{"id": "t1", "title": "T1"}])
        start_execution("M2", [{"id": "t2", "title": "T2"}])
        lst = list_executions()
        assert len(lst) == 2

    def test_pause_execution(self):
        from backend.execution.routes import start_execution, pause_execution, _reset_controller
        _reset_controller()
        result = start_execution("Test", [{"id": "t1", "title": "Test"}])
        # Need to manipulate state to RUNNING for pause to work
        from backend.execution.routes import _controller
        sm = _controller._executions[result["execution_id"]]
        sm.transition(ExecutionState.RUNNING)
        presult = pause_execution(result["execution_id"])
        assert presult["paused"]

    def test_resume_execution(self):
        from backend.execution.routes import start_execution, resume_execution, _reset_controller
        _reset_controller()
        result = start_execution("Test", [{"id": "t1", "title": "Test"}])
        from backend.execution.routes import _controller
        sm = _controller._executions[result["execution_id"]]
        sm.transition(ExecutionState.RUNNING)
        sm.transition(ExecutionState.PAUSED)
        rresult = resume_execution(result["execution_id"])
        assert rresult["resumed"]

    def test_cancel_execution(self):
        from backend.execution.routes import start_execution, cancel_execution, _reset_controller
        _reset_controller()
        result = start_execution("Test", [{"id": "t1", "title": "Test"}])
        cr = cancel_execution(result["execution_id"])
        assert cr["cancelled"]

    def test_get_timeline(self):
        from backend.execution.routes import start_execution, get_timeline, _reset_controller
        _reset_controller()
        result = start_execution("Test", [{"id": "t1", "title": "Test"}])
        tl = get_timeline(result["execution_id"])
        assert tl is not None
        assert "state" in tl

    def test_statistics(self):
        from backend.execution.routes import start_execution, statistics, _reset_controller
        _reset_controller()
        start_execution("Test", [{"id": "t1", "title": "Test"}])
        s = statistics()
        assert s["total_executions"] >= 1


# ═══════════════════════════════════════════════════════════════
# Thread Safety
# ═══════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_task_registration(self):
        ts = TaskScheduler()
        errors = []

        def register_batch(prefix: str, count: int):
            try:
                for i in range(count):
                    ts.register_task(make_task(f"{prefix}-{i}", f"Task {prefix} {i}"))
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=register_batch, args=("A", 25)),
            threading.Thread(target=register_batch, args=("B", 25)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent errors: {errors}"
        assert len(ts.get_ready_tasks()) == 50

    def test_concurrent_execution_control(self):
        me = MissionExecutor()
        meta = make_meta("Concurrent test")
        tasks = [make_task(f"t{i}", f"Task {i}") for i in range(20)]
        sm = me.prepare(meta, tasks)

        errors = []

        def run_batch(ids: list[str]):
            try:
                for tid in ids:
                    me.execute_task(sm, tid)
            except Exception as e:
                errors.append(str(e))

        half = 10
        threads = [
            threading.Thread(target=run_batch, args=(list(tasks[:half].keys()) if False else [t.task_id for t in tasks[:half]],)),
            threading.Thread(target=run_batch, args=([t.task_id for t in tasks[half:]],)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent errors: {errors}"

    def test_concurrent_state_machine_transitions(self):
        sm = ExecutionStateMachine(make_meta())
        sm.transition(ExecutionState.PLANNING)
        sm.transition(ExecutionState.READY)
        sm.transition(ExecutionState.RUNNING)

        errors = []

        def toggle():
            try:
                for _ in range(50):
                    sm.transition(ExecutionState.PAUSED)
                    sm.transition(ExecutionState.RUNNING)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=toggle) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent errors: {errors}"
        assert sm.state in {ExecutionState.RUNNING, ExecutionState.PAUSED}
