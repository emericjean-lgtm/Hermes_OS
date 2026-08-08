"""Execution Controller — manages the lifecycle of a single execution."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from .execution_models import (
    ExecutionMeta,
    ExecutionReport,
    TaskExecution,
)
from .execution_state import ExecutionStateMachine
from .mission_executor import MissionExecutor


class ExecutionController:
    """Controls the lifecycle of a single mission execution.

    Manages: start, pause, resume, cancel, checkpoint, rollback.
    Delegates actual execution to MissionExecutor.
    """

    #: Retention cap for _executions/_reports (HOS-069). Before this
    #: controller was wired to the shared execution engine, nothing ever
    #: populated these dicts in real use, so unbounded growth was never a
    #: practical risk. Once every Mission/Autonomous task execution
    #: registers here, an unbounded dict is exactly the RC3 P5 pattern
    #: already fixed elsewhere (TaskScheduler, ValidationEngine, ...).
    MAX_RETAINED_EXECUTIONS = 512

    def __init__(self, executor: MissionExecutor) -> None:
        self._lock = threading.RLock()
        self._executor = executor
        self._executions: OrderedDict[str, ExecutionStateMachine] = OrderedDict()
        self._reports: OrderedDict[str, ExecutionReport] = OrderedDict()

    def start(self, meta: ExecutionMeta, tasks: list[TaskExecution],
              dependencies: dict[str, list[str]] | None = None) -> ExecutionStateMachine:
        """Start a new execution."""
        with self._lock:
            sm = self._executor.prepare(meta, tasks, dependencies)
            self._executions[meta.execution_id] = sm
            self._executions.move_to_end(meta.execution_id)
            while len(self._executions) > self.MAX_RETAINED_EXECUTIONS:
                oldest_id, _ = self._executions.popitem(last=False)
                self._reports.pop(oldest_id, None)
            return sm

    def execute_task(self, execution_id: str, task_id: str) -> dict[str, Any]:
        """Execute a single task within a running execution.

        HOS-069: the lock only guards the registry lookup, not the call
        itself — ``MissionExecutor.execute_task()`` already runs its slow
        inference call outside its own lock (HOS-068), and wrapping that
        call in *this* controller's lock would silently re-serialize every
        concurrent task execution GraphExecutor now dispatches in parallel.
        """
        with self._lock:
            sm = self._executions.get(execution_id)
        if sm is None:
            raise ValueError(f"Execution {execution_id} not found")
        return self._executor.execute_task(sm, task_id)

    def pause(self, execution_id: str) -> bool:
        with self._lock:
            sm = self._executions.get(execution_id)
            return sm is not None and self._executor.pause(sm)

    def resume(self, execution_id: str) -> bool:
        with self._lock:
            sm = self._executions.get(execution_id)
            return sm is not None and self._executor.resume(sm)

    def cancel(self, execution_id: str) -> bool:
        with self._lock:
            sm = self._executions.get(execution_id)
            return sm is not None and self._executor.cancel(sm)

    def finalize(self, execution_id: str) -> ExecutionReport:
        with self._lock:
            sm = self._executions.get(execution_id)
            if sm is None:
                raise ValueError(f"Execution {execution_id} not found")
            report = self._executor.finalize(sm)
            self._reports[execution_id] = report
            self._reports.move_to_end(execution_id)
            while len(self._reports) > self.MAX_RETAINED_EXECUTIONS:
                self._reports.popitem(last=False)
            return report

    def get(self, execution_id: str) -> dict[str, Any] | None:
        with self._lock:
            sm = self._executions.get(execution_id)
            if sm is None:
                return None
            report = self._reports.get(execution_id)
            state_info = {
                "execution_id": execution_id,
                "state": sm.state.value,
                "mission_id": sm._meta.mission_id,
                "user_goal": sm._meta.user_goal,
                "is_terminal": sm.is_terminal(),
                "is_active": sm.is_active(),
            }
            if report:
                state_info["report"] = {
                    "total_tasks": report.total_tasks,
                    "completed_tasks": report.completed_tasks,
                    "failed_tasks": report.failed_tasks,
                    "duration_ms": report.total_duration_ms,
                    "agents_used": report.agents_used,
                    "runtimes_used": report.runtimes_used,
                    "errors": report.errors,
                }
            return state_info

    def get_timeline(self, execution_id: str) -> dict[str, Any] | None:
        with self._lock:
            sm = self._executions.get(execution_id)
            if sm is None:
                return None
            return self._executor.get_timeline(sm)

    def list_executions(self) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(self._executions.keys())
        return [info for eid in ids if (info := self.get(eid)) is not None]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_executions": sum(1 for sm in self._executions.values() if sm.is_active()),
                "completed_executions": len(self._reports),
                "total_executions": len(self._executions),
                "executor_stats": self._executor.stats(),
            }
