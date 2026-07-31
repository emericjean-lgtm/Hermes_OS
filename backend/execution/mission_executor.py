"""Mission Executor — the central execution engine (HOS-050).

Orchestrates the complete pipeline:
    User Goal → Planner → Graph → Scheduler → Agents → Skills → Runtime → Tools → Validation → Memory
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any

from .execution_models import (
    ExecutionMeta,
    ExecutionReport,
    ExecutionState,
    TaskExecution,
    TaskExecutionStatus,
    ValidationOutcome,
)
from .execution_state import ExecutionStateMachine
from .task_scheduler import TaskScheduler
from .agent_coordinator import AgentCoordinator
from .validation_engine import ValidationEngine
from .feedback_loop import FeedbackLoop
from .optimization_engine import OptimizationEngine
from .task_executor import RuntimeUnavailableError

logger = logging.getLogger("hermes_os.execution.mission")


def _unique(values: Any) -> list[str]:
    """Non-empty values, de-duplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values:
        if value:
            seen.setdefault(str(value), None)
    return list(seen)


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

    #: Diagnostic event tail kept in memory. See ``_events``.
    MAX_RETAINED_EVENTS = 2000

    def __init__(self, task_executor: Any = None, on_event: Any = None) -> None:
        """
        Args:
            task_executor: performs the actual work for one task. Injected so the
                engine keeps orchestrating and something else executes — the
                separation the simulated step used to blur. Defaults to
                :class:`~backend.execution.task_executor.RealTaskExecutor`.
            on_event: the shared event dispatcher.
        """
        self._lock = threading.RLock()
        self._scheduler = TaskScheduler()
        self._coordinator = AgentCoordinator()
        self._validator = ValidationEngine()
        self._feedback = FeedbackLoop()
        self._optimizer = OptimizationEngine()
        # Ring buffer: this is a diagnostic tail for get_events(), not an
        # archive. Unbounded, it grew 5 entries per mission forever — 4000
        # dicts after 800 missions, the single largest allocation site in a
        # load run (RC3 P5). Durable history belongs to SystemEventBus.
        self._events: deque[dict[str, Any]] = deque(maxlen=self.MAX_RETAINED_EVENTS)
        # execution_id -> its own task ids. Bounded like everything else here:
        # the scheduler retains a fixed window, so this must not outgrow it.
        self._execution_tasks: OrderedDict[str, list[str]] = OrderedDict()
        self._on_event = on_event

        if task_executor is None:
            from .task_executor import RealTaskExecutor

            task_executor = RealTaskExecutor(on_event=on_event)
        self._task_executor = task_executor

    # ── Public API ──

    def prepare(self, meta: ExecutionMeta, tasks: list[TaskExecution],
                dependencies: dict[str, list[str]] | None = None) -> ExecutionStateMachine:
        """Prepare execution: register tasks with dependencies, build schedule plan."""
        with self._lock:
            sm = ExecutionStateMachine(meta)
            sm.transition(ExecutionState.PLANNING, "Preparing execution")

            # Remember which tasks belong to *this* execution. The scheduler is
            # shared by every mission in the process, so finalize() cannot tell
            # them apart from the registry alone and would report one mission's
            # figures over every task ever registered (R-002 P5).
            self._execution_tasks[meta.execution_id] = [t.task_id for t in tasks]
            while len(self._execution_tasks) > self._scheduler.MAX_RETAINED_TASKS:
                self._execution_tasks.popitem(last=False)

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
            # The scheduler already keys tasks by id. This used to copy the whole
            # registry and linear-scan it, making each execution O(tasks-ever-
            # registered) and the engine as a whole O(n²): throughput fell from
            # 1012 to 454 missions/s across a 1000-mission run (RC3 P5).
            task = self._scheduler.get_task(task_id)

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

            # 2. Execute for real — this is the "calls the agent via runtime"
            #    that the previous comment promised and never did. A task that
            #    cannot run now fails; it does not report an invented result.
            try:
                outcome = self._task_executor.execute(task, assignment)
            except RuntimeUnavailableError as exc:
                task.status = TaskExecutionStatus.FAILED
                task.errors.append(str(exc))
                task.completed_at = datetime.now(timezone.utc)
                task.duration_ms = (
                    (task.completed_at - task.started_at).total_seconds() * 1000.0
                    if task.started_at else 0.0
                )
                self._publish("execution.failed", {
                    "task_id": task_id, "reason": "runtime_unavailable",
                    "detail": str(exc),
                })
                self._scheduler.update_task(task_id, task.status)
                self._coordinator.release_agent(task_id)
                return {
                    "task_id": task_id,
                    "status": task.status.value,
                    "error": str(exc),
                    "runtime_available": False,
                }

            task.result = outcome.result
            task.duration_ms = outcome.duration_ms
            task.assigned_runtime = outcome.runtime_id
            task.resources_used = outcome.resources()
            task.completed_at = datetime.now(timezone.utc)

            # 3. Validate
            sm.transition(ExecutionState.VALIDATING, f"Validating task {task_id}")
            outcome = self._validator.validate(task)
            task.validation_outcome = outcome

            if outcome == ValidationOutcome.PASS:
                task.status = TaskExecutionStatus.COMPLETED
                # Not dispatched: RealTaskExecutor already publishes
                # execution.task_completed for this task, with richer detail
                # (runtime, model, duration, tokens). Announcing it again here
                # made subscribers count every task twice.
                self._publish("execution.task_completed",
                              {"task_id": task_id, "outcome": "pass"},
                              dispatch=False)
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

            # Every figure below is measured. total_duration_ms used to be
            # `42.0 * progress["total"]` — a constant per task, marked
            # "# simulated" — and this report is fed straight into
            # self._feedback.analyze(), so the feedback loop was learning from a
            # fabricated number. The runtime/skill/tool lists were hard-coded
            # empty even though every assignment records them (R-002 P5).
            task_ids = self._execution_tasks.get(sm._meta.execution_id, [])
            tasks = [t for t in (self._scheduler.get_task(tid) for tid in task_ids)
                     if t is not None]
            runtimes = _unique(t.assigned_runtime for t in tasks)
            skills = _unique(s for t in tasks for s in (t.assigned_skills or []))
            tools = _unique(s for t in tasks for s in (t.assigned_tools or []))
            agents = _unique(t.assigned_agent for t in tasks) or list(sm._meta.tags)

            report = ExecutionReport(
                execution_id=sm._meta.execution_id,
                mission_id=sm._meta.mission_id,
                state=sm.state,
                total_tasks=progress["total"],
                completed_tasks=progress["completed"],
                failed_tasks=progress["failed"],
                total_duration_ms=sum(t.duration_ms or 0.0 for t in tasks),
                agents_used=agents,
                runtimes_used=runtimes,
                skills_used=skills,
                tools_used=tools,
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

    # ── Event publication ──

    def _publish(self, event_type: str, data: dict[str, Any],
                 dispatch: bool = True) -> None:
        """Record an event locally and dispatch it to the shared event bus.

        The dispatch half used to be missing: ``on_event`` was accepted,
        documented as "the shared event dispatcher", stored — and never called.
        Every mission lifecycle event was appended to this private list and went
        nowhere, so the Cockpit's live feed never saw a mission start, a task
        start or a mission completion (RC3 P2). Only the one event
        ``RealTaskExecutor`` emits itself was reaching subscribers.

        Args:
            dispatch: set False for milestones a collaborator already announces
                on the same topic, so subscribers do not see it twice. The event
                is still recorded in the local diagnostic tail either way.
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        self._events.append(event)

        if not dispatch or self._on_event is None:
            return
        try:
            self._on_event(event_type, event)
        except Exception:
            # Telemetry must never fail the mission it is describing.
            logger.warning("event dispatch failed for %s", event_type, exc_info=True)

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
