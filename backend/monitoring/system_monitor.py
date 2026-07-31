"""System Monitor for Hermes OS (HOS-062).

Tracks CPU, RAM, disk, and service health metrics
with periodic sampling and alerting.
"""

from __future__ import annotations

import shutil
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable


class SystemMonitor:
    """Monitors system resources and service health."""

    def __init__(self, interval_s: int = 30, max_history: int = 1000):
        self._interval_s = interval_s
        self._max_history = max_history
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._alerts: deque = deque(maxlen=100)
        self._alert_callbacks: list[Callable] = []
        self._services: dict[str, dict[str, Any]] = {}

    # ── Public API ──

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def register_service(self, name: str, check_fn: Callable[[], bool]) -> None:
        self._services[name] = {"check": check_fn, "status": "unknown", "last_check": 0}

    def get_metric(self, name: str) -> list:
        with self._lock:
            return list(self._metrics.get(name, []))

    def get_all_metrics(self) -> dict[str, list]:
        with self._lock:
            return {k: list(v) for k, v in self._metrics.items()}

    def get_alerts(self, limit: int = 20) -> list:
        return list(self._alerts)[-limit:]

    def get_service_status(self) -> dict[str, str]:
        return {name: info["status"] for name, info in self._services.items()}

    def on_alert(self, callback: Callable) -> None:
        self._alert_callbacks.append(callback)

    def collect_once(self) -> dict[str, Any]:
        """Collect a single snapshot of system metrics."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": self._get_cpu_percent(),
            "memory_percent": self._get_memory_percent(),
            "memory_available_mb": self._get_memory_available_mb(),
            "disk_percent": self._get_disk_percent(),
            "disk_free_gb": self._get_disk_free_gb(),
            "services": self._get_service_snapshot(),
            "thread_count": threading.active_count(),
        }
        return snapshot

    def is_healthy(self) -> bool:
        """Overall system health check."""
        try:
            snap = self.collect_once()
            if snap["memory_percent"] > 95:
                return False
            if snap["disk_percent"] > 95:
                return False
            if snap["cpu_percent"] > 95:
                return False
            return True
        except Exception:
            return False

    # ── Private ──

    def _loop(self) -> None:
        while self._running:
            try:
                snapshot = self.collect_once()
                with self._lock:
                    for key, value in snapshot.items():
                        if isinstance(value, (int, float)):
                            self._metrics[key].append((time.time(), value))
                self._check_alerts(snapshot)
                self._check_services()
            except Exception as e:
                self._alerts.append({
                    "type": "monitor_error",
                    "message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            time.sleep(self._interval_s)

    def _get_cpu_percent(self) -> float:
        try:
            with open("/proc/stat") as f:
                cpu_line = f.readline().strip().split()
                if cpu_line[0] == "cpu" and len(cpu_line) >= 5:
                    user, nice, system, idle = int(cpu_line[1]), int(cpu_line[2]), int(cpu_line[3]), int(cpu_line[4])
                    total = user + nice + system + idle
                    return 100.0 * (total - idle) / total if total > 0 else 0.0
        except (OSError, IndexError, ValueError):
            pass
        return 0.0

    def _get_memory_percent(self) -> float:
        try:
            with open("/proc/meminfo") as f:
                total = available = 0
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        available = int(line.split()[1])
                if total > 0:
                    return 100.0 * (total - available) / total
        except (OSError, IndexError, ValueError):
            pass
        return 0.0

    def _get_memory_available_mb(self) -> float:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / 1024.0
        except (OSError, IndexError, ValueError):
            pass
        return 0.0

    # shutil.disk_usage rather than os.statvfs: statvfs does not exist on
    # Windows, so the attribute lookup raised AttributeError — which the
    # OSError handler below did not catch — and took collect_once() down
    # with it. disk_usage reports the same totals on every platform.
    def _get_disk_percent(self) -> float:
        try:
            usage = shutil.disk_usage(".")
            if usage.total > 0:
                return 100.0 * usage.used / usage.total
        except OSError:
            pass
        return 0.0

    def _get_disk_free_gb(self) -> float:
        try:
            return shutil.disk_usage(".").free / (1024**3)
        except OSError:
            return 0.0

    def _get_service_snapshot(self) -> dict[str, str]:
        result = {}
        for name, info in self._services.items():
            result[name] = info["status"]
        return result

    def _check_services(self) -> None:
        now = time.time()
        for name, info in self._services.items():
            if now - info.get("last_check", 0) < self._interval_s:
                continue
            try:
                ok = info["check"]()
                info["status"] = "healthy" if ok else "degraded"
            except Exception:
                info["status"] = "unreachable"
            info["last_check"] = now

    def _check_alerts(self, snapshot: dict[str, Any]) -> None:
        alerts = []
        if snapshot["memory_percent"] > 90:
            alerts.append(("WARNING", f"Memory usage at {snapshot['memory_percent']:.0f}%"))
        if snapshot["disk_percent"] > 90:
            alerts.append(("WARNING", f"Disk usage at {snapshot['disk_percent']:.0f}%"))
        if snapshot["cpu_percent"] > 90:
            alerts.append(("WARNING", f"CPU usage at {snapshot['cpu_percent']:.0f}%"))
        for level, msg in alerts:
            alert = {"type": level, "message": msg, "timestamp": snapshot["timestamp"]}
            self._alerts.append(alert)
            for cb in self._alert_callbacks:
                try:
                    cb(alert)
                except Exception:
                    pass
