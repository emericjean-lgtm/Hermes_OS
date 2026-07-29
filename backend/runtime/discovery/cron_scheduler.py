"""Cron Scheduler for the Discovery Engine (HOS-040).

Schedules periodic discovery scans and benchmark runs.
"""

from __future__ import annotations

import threading
import time as _time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class TaskType(str, Enum):
    DISCOVERY = "discovery"
    BENCHMARK = "benchmark"
    COMPATIBILITY = "compatibility"


class CronScheduler:
    """Simple in-process cron scheduler for periodic tasks.

    Thread-safe. No external dependencies.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[dict[str, Any]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_runs: dict[str, datetime] = {}

    def schedule(
        self,
        task_type: TaskType,
        interval_seconds: float,
        callback: Callable[[], None],
        name: str = "",
    ) -> str:
        """Schedule a periodic task.

        Returns the task name for later management.
        """
        task_name = name or f"{task_type.value}-{len(self._tasks)}"
        with self._lock:
            self._tasks.append({
                "name": task_name,
                "type": task_type,
                "interval": interval_seconds,
                "callback": callback,
            })
        return task_name

    def start(self) -> None:
        """Start the scheduler loop in a background thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=2.0)
                self._thread = None

    def _loop(self) -> None:
        while self._running:
            now = datetime.now(timezone.utc)
            with self._lock:
                tasks = list(self._tasks)
            for task in tasks:
                last = self._last_runs.get(task["name"])
                if last is None or (now - last).total_seconds() >= task["interval"]:
                    try:
                        task["callback"]()
                    except Exception:
                        pass
                    self._last_runs[task["name"]] = now
            _time.sleep(1.0)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "tasks_count": len(self._tasks),
                "tasks": [
                    {"name": t["name"], "type": t["type"].value, "interval_s": t["interval"]}
                    for t in self._tasks
                ],
                "last_runs": {
                    name: dt.isoformat() for name, dt in self._last_runs.items()
                },
            }
