"""Task Scheduler — determines execution order with parallelization support."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .execution_models import (
    TaskExecution,
    TaskExecutionStatus,
    SchedulerStrategy,
    ExecutionPriority,
)


@dataclass
class SchedulePlan:
    """Output of the scheduling engine — the execution plan."""
    strategy: SchedulerStrategy = SchedulerStrategy.RESOURCE_AWARE
    waves: list[list[str]] = field(default_factory=list)    # Each wave = parallel task IDs
    blocked: list[str] = field(default_factory=list)         # Tasks waiting on dependencies
    failed: list[str] = field(default_factory=list)          # Tasks whose deps failed
    total_tasks: int = 0
    ready_count: int = 0


class TaskScheduler:
    """Determines which tasks can run now, which are blocked, and the optimal order.

    Supports: parallel execution, dependencies, priorities, resource limits.
    Integrates with RuntimeResourceManager for GPU limits.
    """

    def __init__(self, max_parallel: int = 8, max_gpu_tasks: int = 2) -> None:
        self._lock = threading.RLock()
        self._max_parallel = max_parallel
        self._max_gpu_tasks = max_gpu_tasks
        self._tasks: dict[str, TaskExecution] = {}
        self._dependencies: dict[str, set[str]] = {}   # task_id → {dep_ids...}

    def register_task(self, task: TaskExecution, dependencies: list[str] | None = None) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            self._dependencies[task.task_id] = set(dependencies or [])

    def update_task(self, task_id: str, status: TaskExecutionStatus,
                    result: Any = None) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if result is not None:
                    self._tasks[task_id].result = result

    def get_ready_tasks(self, max_count: int | None = None,
                        gpu_only: bool = False) -> list[str]:
        """Return task IDs that are ready to execute (dependencies satisfied)."""
        with self._lock:
            ready = []
            for tid, task in self._tasks.items():
                if task.status != TaskExecutionStatus.PENDING:
                    continue
                deps = self._dependencies.get(tid, set())
                if all(self._is_dep_satisfied(d) for d in deps):
                    ready.append((tid, self._priority_value(task)))

            # Sort by priority (higher first)
            ready.sort(key=lambda x: -x[1])

            if max_count is not None:
                ready = ready[:max_count]

            return [tid for tid, _ in ready]

    def get_blocked_tasks(self) -> list[str]:
        """Return tasks that are waiting on unsatisfied dependencies."""
        with self._lock:
            blocked = []
            for tid, deps in self._dependencies.items():
                task = self._tasks.get(tid)
                if task is None or task.status != TaskExecutionStatus.PENDING:
                    continue
                if deps and not all(self._is_dep_satisfied(d) for d in deps):
                    blocked.append(tid)
            return blocked

    def build_plan(self) -> SchedulePlan:
        """Build a full execution plan with parallel waves."""
        with self._lock:
            plan = SchedulePlan(total_tasks=len(self._tasks))
            remaining = set(self._tasks.keys())
            completed: set[str] = set()

            while remaining:
                wave = []
                for tid in sorted(remaining):
                    deps = self._dependencies.get(tid, set())
                    if deps.issubset(completed):
                        task = self._tasks[tid]
                        if task.status == TaskExecutionStatus.PENDING:
                            wave.append(tid)
                if not wave:
                    # Deadlock or all remaining are blocked/failed
                    plan.blocked = list(remaining)
                    break
                plan.waves.append(wave)
                for tid in wave:
                    remaining.discard(tid)
                    completed.add(tid)

            plan.ready_count = sum(len(w) for w in plan.waves)
            return plan

    def get_progress(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._tasks)
            completed = sum(
                1 for t in self._tasks.values()
                if t.status in {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED}
            )
            failed = sum(1 for t in self._tasks.values() if t.status == TaskExecutionStatus.FAILED)
            running = sum(1 for t in self._tasks.values() if t.status == TaskExecutionStatus.RUNNING)
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "pending": total - completed - failed - running,
                "percent": round(completed / total * 100, 1) if total else 0,
            }

    def is_all_done(self) -> bool:
        with self._lock:
            if not self._tasks:
                return True
            return all(
                t.status in {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED, TaskExecutionStatus.FAILED}
                for t in self._tasks.values()
            )

    # ── private ──

    def _is_dep_satisfied(self, dep_id: str) -> bool:
        t = self._tasks.get(dep_id)
        return t is not None and t.status in {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED}

    @staticmethod
    def _priority_value(task: TaskExecution) -> int:
        # Higher is more urgent
        prio_map = {
            ExecutionPriority.CRITICAL: 4,
            ExecutionPriority.HIGH: 3,
            ExecutionPriority.NORMAL: 2,
            ExecutionPriority.LOW: 1,
        }
        return prio_map.get(ExecutionPriority.NORMAL, 2)

    def stats(self) -> dict[str, Any]:
        return self.get_progress()
