"""Memory Manager for the Runtime Resource Manager (HOS-035).

Tracks system RAM usage via /proc/meminfo (Linux) or psutil.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from backend.runtime.resources.resource_models import (
    ResourceSnapshot,
    ResourceStatus,
    ResourceType,
)


class MemoryManager:
    """Tracks system RAM usage. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Optional[ResourceSnapshot] = None
        self._last_update: Optional[datetime] = None
        self._update_interval_s: float = 1.0

    def poll(self) -> ResourceSnapshot:
        """Fetch current RAM usage."""
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._last_update and (
                now - self._last_update
            ).total_seconds() < self._update_interval_s:
                return self._snapshot  # type: ignore[return-value]
            self._snapshot = self._poll_now()
            self._last_update = now
            return self._snapshot

    def _poll_now(self) -> ResourceSnapshot:
        total, used = self._read_meminfo()
        free = max(0, total - used)
        return ResourceSnapshot(
            resource_type=ResourceType.RAM,
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,
            status=ResourceStatus.HEALTHY,
        )

    def _read_meminfo(self) -> tuple[int, int]:
        """Parse /proc/meminfo for total and available memory (bytes)."""
        mem_total = 0
        mem_available = 0
        mem_free = 0
        buffers = 0
        cached = 0

        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) * 1024
                    elif line.startswith("MemAvailable:"):
                        mem_available = int(line.split()[1]) * 1024
                    elif line.startswith("MemFree:"):
                        mem_free = int(line.split()[1]) * 1024
                    elif line.startswith("Buffers:"):
                        buffers = int(line.split()[1]) * 1024
                    elif line.startswith("Cached:"):
                        cached = int(line.split()[1]) * 1024
                    if mem_total > 0 and (mem_available > 0 or mem_free > 0):
                        # Have enough to compute
                        pass

            if mem_available > 0:
                used = mem_total - mem_available
            else:
                used = mem_total - mem_free - buffers - cached
            return mem_total, max(0, used)
        except FileNotFoundError:
            # Non-Linux fallback: use psutil if available
            pass

        return self._psutil_fallback()

    def _psutil_fallback(self) -> tuple[int, int]:
        """Fallback using psutil if installed."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.total, mem.used
        except ImportError:
            pass
        return 0, 0
