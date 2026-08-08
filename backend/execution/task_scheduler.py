"""Task Scheduler — determines execution order with parallelization support."""

from __future__ import annotations

import threading
from collections import OrderedDict
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

    Supports: parallel execution, dependencies, priorities.

    Does NOT integrate with RuntimeResourceManager, despite an earlier
    version of this docstring claiming it did — ``max_parallel``/
    ``max_gpu_tasks``/``get_ready_tasks()``'s ``gpu_only`` parameter are all
    accepted but never read anywhere in this class (found during the
    HOS-069 Execution Center audit). Real, GPU-telemetry-backed VRAM
    admission checking lives in ``RealTaskExecutor._check_vram_admission()``
    (task_executor.py) instead, gated by a real ``ResourceManager``
    (backend/runtime/resources/resource_manager.py) wired at bootstrap — it
    runs per real inference call, not per scheduling decision, because the
    model a task will use isn't known until deep inside execution (agent
    coordination -> model resolution), well past this scheduler's own
    get_ready_tasks()/build_plan(). Those two methods, along with priority
    ordering, are also not on the path real Mission/Autonomous executions
    take at all — see GraphExecutor's own DependencyResolver, a separate,
    independent dependency graph this scheduler's is a near-duplicate of.
    """

    #: Tasks retained after completion. The scheduler is a live work queue, not
    #: an archive: get_progress(), is_all_done() and build_plan() each walk this
    #: registry, and they run once per task execution. Unbounded, that made them
    #: O(missions-ever-run) and throughput decayed from 983 to 256 missions/s
    #: over a 3100-mission run (RC3 P5). Bounding it makes the same scans
    #: constant-cost. Sized as a diagnostic window over recent work — durable
    #: task history belongs to episodic memory, not to the scheduler.
    MAX_RETAINED_TASKS = 512

    _TERMINAL = frozenset({TaskExecutionStatus.COMPLETED,
                           TaskExecutionStatus.SKIPPED,
                           TaskExecutionStatus.FAILED})

    def __init__(self, max_parallel: int = 8, max_gpu_tasks: int = 2) -> None:
        # max_parallel/max_gpu_tasks: accepted for API compatibility with
        # existing callers/tests, but unused — see the class docstring.
        self._lock = threading.RLock()
        self._max_parallel = max_parallel
        self._max_gpu_tasks = max_gpu_tasks
        self._tasks: OrderedDict[str, TaskExecution] = OrderedDict()
        self._dependencies: dict[str, set[str]] = {}   # task_id → {dep_ids...}

    def register_task(self, task: TaskExecution, dependencies: list[str] | None = None) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            self._tasks.move_to_end(task.task_id)
            self._dependencies[task.task_id] = set(dependencies or [])
            self._evict_oldest()

    def get_task(self, task_id: str) -> TaskExecution | None:
        """Look up one registered task. O(1) — callers used to linear-scan."""
        with self._lock:
            return self._tasks.get(task_id)

    #: How many still-pending tasks eviction will rotate to the back before it
    #: starts discarding them. Keeps eviction O(1) amortised instead of scanning
    #: the whole registry for terminal candidates on every registration.
    _EVICT_RESCUE_LIMIT = 16

    def _evict_oldest(self) -> None:
        """Drop the oldest tasks once past the retention cap. Lock held.

        Finished work is discarded before pending work: an oldest-first pop that
        lands on a still-queued task rotates it to the back instead of dropping
        it. That rescue is bounded, so the retention cap stays a hard memory
        bound even if every retained task is pending.
        """
        overflow = len(self._tasks) - self.MAX_RETAINED_TASKS
        if overflow <= 0:
            return
        rescued = 0
        while overflow > 0 and self._tasks:
            tid, task = self._tasks.popitem(last=False)
            if task.status not in self._TERMINAL and rescued < self._EVICT_RESCUE_LIMIT:
                self._tasks[tid] = task
                rescued += 1
                continue
            self._dependencies.pop(tid, None)
            overflow -= 1

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
        # Walks the retained registry. Kept as a straight scan on purpose: task
        # status is assigned directly by callers as well as through
        # update_task(), so any maintained tally would silently drift, and a
        # terminal task is not guaranteed never to be re-executed. What made
        # this expensive was the registry growing without bound (RC3 P5); the
        # scan is now O(MAX_RETAINED_TASKS), i.e. constant, not O(missions run).
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
            return all(t.status in self._TERMINAL for t in self._tasks.values())

    def all_done(self, task_ids: list[str]) -> bool:
        """Like ``is_all_done()`` but scoped to a specific set of tasks.

        HOS-069: this scheduler is shared by every execution in the process
        (one registry, many callers), so ``is_all_done()`` only answers "is
        literally every task ever registered here terminal" — with more than
        one execution in flight (real since HOS-068's parallel GraphExecutor
        dispatch), that is almost never true for any *one* of them.
        MissionExecutor.execute_task() needs "are this execution's own tasks
        done", which is what this answers instead.
        """
        with self._lock:
            if not task_ids:
                return False
            return all(
                (t := self._tasks.get(tid)) is not None and t.status in self._TERMINAL
                for tid in task_ids
            )

    # ── private ──

    def _is_dep_satisfied(self, dep_id: str) -> bool:
        t = self._tasks.get(dep_id)
        return t is not None and t.status in {TaskExecutionStatus.COMPLETED, TaskExecutionStatus.SKIPPED}

    @staticmethod
    def _priority_value(task: TaskExecution) -> int:
        """Rank one task for the ready-queue sort. Higher is more urgent.

        KNOWN LIMITATION (RC3 P5, deliberately not fixed here): this returns the
        same value for every task, so the sort in get_ready_tasks() is inert and
        a CRITICAL mission's tasks do not outrank a LOW one's. The cause is a
        model gap, not a typo — ``priority`` lives on ``ExecutionMeta`` (per
        mission, set by the API) and ``TaskExecution`` carries no priority at
        all, so there is nothing here to rank by. Closing it means propagating
        the mission priority onto each task, which is new behaviour and out of
        scope for an audit. Documented in the RC3 report instead.
        """
        prio_map = {
            ExecutionPriority.CRITICAL: 4,
            ExecutionPriority.HIGH: 3,
            ExecutionPriority.NORMAL: 2,
            ExecutionPriority.LOW: 1,
        }
        return prio_map.get(ExecutionPriority.NORMAL, 2)

    def stats(self) -> dict[str, Any]:
        return self.get_progress()
