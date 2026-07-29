"""Mission Executor — the central execution engine (HOS-050).

Orchestrates the complete pipeline:
    User Goal → Planner → Graph → Scheduler → Agents → Skills → Runtime → Tools → Validation → Memory
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .execution_models import (
    ExecutionMeta,
    ExecutionReport,
    ExecutionState,
    ExecutionTimeline,
    TaskExecution,
    TaskExecutionStatus,
    ValidationOutcome,
)
from .execution_state import ExecutionStateMachine
from .task_scheduler import TaskScheduler
from .agent_coordinator import AgentCoordinator, AgentAssignment
from .validation_engine import ValidationEngine
from .feedback_loop import FeedbackLoop
from .optimization_engine import OptimizationEngine


class MissionExecutor:
    """Central execution engine that orchestrates a full mission from user goal to completion.

    Pipeline:
        1. Planning — transforms user goal into tasks (via Mission Planner integration)
        2. Scheduling — determines execution order with parallelization
        3. Assignment — assigns agents, skills, runtimes, tools
        4. Execution — runs tasks with validation after each
        5. Feedback — analyzes outcomes and feeds into Memory/Intelligence
        6. Optimization — identifies improvements for future missions
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scheduler = TaskScheduler()
        self._coordinator = AgentCoordinator()
        self._validator = ValidationEngine()
        self._feedback = FeedbackLoop()
        self._optimizer = OptimizationEngine()
        self._events: list[dict[str, Any]] = []  # Simulated EventBus

    # ── Public API ──

    def prepare(self, meta: ExecutionMeta, tasks: list[TaskExecution],
                dependencies: dict[str, list[str]] | None = None) -> ExecutionStateMachine:
        """Prepare execution: register tasks with dependencies, build schedule plan."""
        with self._lock:
            sm = ExecutionStateMachine(meta)
            sm.transition(ExecutionState.PLANNING, "Preparing execution")

            for task in tasks:
                deps = (dependencies or {}).get(task.task_id, [])
                self._scheduler.register_task(task, deps)

            self._publish("execution.started", {"execution_id": meta.execution_id})
            self._publish("execution.planning", {"execution_id": meta.execution_id})

            sm.transition(ExecutionState.READY, "Tasks registered and scheduled")
            return sm

    def execute_task(self, sm: ExecutionStateMachine, task_id: str) -> dict[str, Any]:
        """Execute a single task through the full pipeline."""
        with self._lock:
            assignments = list(self._scheduler._tasks.values())
            task = None
            for t in assignments:
                if t.task_id == task_id:
                    task = t
                    break

            if task is None:
                return {"task_id": task_id, "status": "not_found"}

            sm.transition(ExecutionState.RUNNING, f"Executing task {task_id}")
            self._publish("execution.task_started", {"task_id": task_id})

            # 1. Coordinate: select agent, skills, runtime, tools
            assignment = self._coordinator.assign(task)
            task.assigned_agent = assignment.agent_id
            task.assigned_runtime = assignment.runtime_id
            task.assigned_skills = assignment.skill_ids
            task.assigned_tools = assignment.tool_ids
            task.status = TaskExecutionStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)

            # 2. Simulate execution (in real system, this calls the agent via runtime)
            task.result = f"Simulated result for: {task.title}"
            task.duration_ms = 42.0  # simulated
            task.completed_at = datetime.now(timezone.utc)

            # 3. Validate
            sm.transition(ExecutionState.VALIDATING, f"Validating task {task_id}")
            outcome = self._validator.validate(task)
            task.validation_outcome = outcome

            if outcome == ValidationOutcome.PASS:
                task.status = TaskExecutionStatus.COMPLETED
                self._publish("execution.task_completed", {"task_id": task_id, "outcome": "pass"})
            elif outcome == ValidationOutcome.RETRY:
                if task.retries < 3:  # max_retries
                    task.retries += 1
                    task.status = TaskExecutionStatus.PENDING
                    task.errors.append("Retry after validation")
                else:
                    task.status = TaskExecutionStatus.FAILED
                    self._publish("execution.failed", {"task_id": task_id, "reason": "Max retries"})
            elif outcome == ValidationOutcome.FAIL:
                task.status = TaskExecutionStatus.FAILED
                self._publish("execution.failed", {"task_id": task_id, "reason": "Validation failed"})
            elif outcome == ValidationOutcome.NEEDS_REVIEW:
                sm.transition(ExecutionState.WAITING_APPROVAL, "Needs human review")
                self._publish("execution.waiting_approval", {"task_id": task_id})

            # Update scheduler
            self._scheduler.update_task(task_id, task.status)

            # Release agent
            self._coordinator.release_agent(task_id)

            if self._scheduler.is_all_done():
                sm.transition(ExecutionState.COMPLETED, "All tasks completed")
                self._publish("execution.completed", {"execution_id": sm._meta.execution_id})

            return {
                "task_id": task_id,
                "status": task.status.value,
                "agent": task.assigned_agent,
                "runtime": task.assigned_runtime,
                "skills": task.assigned_skills,
                "tools": task.assigned_tools,
                "outcome": task.validation_outcome.value if task.validation_outcome else None,
                "duration_ms": task.duration_ms,
            }

    def finalize(self, sm: ExecutionStateMachine) -> ExecutionReport:
        """Produce final report and trigger feedback + optimization."""
        with self._lock:
            progress = self._scheduler.get_progress()

            report = ExecutionReport(
                execution_id=sm._meta.execution_id,
                mission_id=sm._meta.mission_id,
                state=sm.state,
                total_tasks=progress["total"],
                completed_tasks=progress["completed"],
                failed_tasks=progress["failed"],
                total_duration_ms=42.0 * progress["total"],  # simulated
                agents_used=list(sm._meta.tags),
                runtimes_used=[],
                skills_used=[],
                tools_used=[],
            )

            # Feedback into Memory / Intelligence
            self._feedback.analyze(report)
            self._optimizer.record_execution(report.execution_id, {
                "state": report.state.value,
                "total_tasks": report.total_tasks,
                "failed_tasks": report.failed_tasks,
            })

            recs = self._optimizer.generate_recommendations()
            if recs:
                self._publish("execution.optimized", {"execution_id": report.execution_id, "recommendations": len(recs)})

            return report

    def pause(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if sm.state == ExecutionState.RUNNING:
                sm.transition(ExecutionState.PAUSED, "User requested pause")
                return True
            return False

    def resume(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if sm.state == ExecutionState.PAUSED:
                sm.transition(ExecutionState.RUNNING, "User requested resume")
                return True
            return False

    def cancel(self, sm: ExecutionStateMachine) -> bool:
        with self._lock:
            if not sm.is_terminal():
                sm.transition(ExecutionState.CANCELLED, "User requested cancel")
                return True
            return False

    def get_timeline(self, sm: ExecutionStateMachine) -> dict[str, Any]:
        with self._lock:
            progress = self._scheduler.get_progress()
            history = [{"from": old.value, "to": new.value, "reason": reason}
                       for old, new, reason in sm.history]
            return {
                "execution_id": sm._meta.execution_id,
                "state": sm.state.value,
                "progress": progress,
                "history": history,
                "events_count": len(self._events),
            }

    def get_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    # ── EventBus simulation ──

    def _publish(self, event_type: str, data: dict[str, Any]) -> None:
        self._events.append({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        })

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "scheduler": self._scheduler.stats(),
                "coordinator": self._coordinator.stats(),
                "validator": self._validator.stats(),
                "feedback": self._feedback.stats(),
                "optimizer": self._optimizer.stats(),
                "events_published": len(self._events),
            }
