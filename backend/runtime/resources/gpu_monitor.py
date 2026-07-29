"""GPU Monitor for the Runtime Resource Manager (HOS-035).

Provides GPU/VRAM/temperature monitoring with a no-op fallback
for environments without a GPU (CI, docker, CPU-only).
"""

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.runtime.resources.resource_models import GPUInfo, ResourceStatus


class GPUMonitor:
    """Monitor GPU resources (VRAM, temperature, utilisation).

    Uses rocm-smi on AMD or nvidia-smi on NVIDIA when available.
    Falls back to ollama ps for VRAM estimates otherwise.
    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._info: GPUInfo = GPUInfo()
        self._last_update: Optional[datetime] = None
        self._update_interval_s: float = 2.0
        self._on_alert: Optional[Callable[[GPUInfo], None]] = None

    def set_alert_handler(self, handler: Callable[[GPUInfo], None]) -> None:
        """Register a callback for when GPU enters warning/critical state."""
        self._on_alert = handler

    def poll(self) -> GPUInfo:
        """Fetch current GPU state. Thread-safe."""
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._last_update and (
                now - self._last_update
            ).total_seconds() < self._update_interval_s:
                return self._info
            self._info = self._poll_now()
            self._last_update = now
            return self._info

    def _poll_now(self) -> GPUInfo:
        """Internal: attempt various monitoring methods."""
        info = self._try_rocm_smi()
        if info is not None:
            return info
        info = self._try_nvidia_smi()
        if info is not None:
            return info
        info = self._try_ollama_ps()
        if info is not None:
            return info
        return GPUInfo(available=False)

    def _try_rocm_smi(self) -> Optional[GPUInfo]:
        """Attempt to query AMD GPU via rocm-smi."""
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            import json
            data = json.loads(result.stdout)
            for card_id, card_data in data.items():
                # Fields vary by rocm-smi version
                vram_total = _find_int(card_data, "VRAM Total Memory (B)", "VRAM Total")
                vram_used = _find_int(card_data, "VRAM Total Used Memory (B)", "VRAM Used")
                vram_free = max(0, vram_total - vram_used)
                return GPUInfo(
                    name=f"AMD-{card_id}",
                    vendor="AMD",
                    vram_total_bytes=vram_total,
                    vram_used_bytes=vram_used,
                    vram_free_bytes=vram_free,
                    available=True,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None

    def _try_nvidia_smi(self) -> Optional[GPUInfo]:
        """Attempt to query NVIDIA GPU via nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            parts = result.stdout.strip().split(",")
            return GPUInfo(
                name=parts[0].strip(),
                vendor="NVIDIA",
                vram_total_bytes=int(float(parts[1])) * 1024 * 1024,
                vram_used_bytes=int(float(parts[2])) * 1024 * 1024,
                vram_free_bytes=int(float(parts[3])) * 1024 * 1024,
                temperature_celsius=(
                    float(parts[4]) if len(parts) > 4 and parts[4].strip() != "[N/A]" else None
                ),
                utilization_pct=(
                    float(parts[5]) if len(parts) > 5 and parts[5].strip() != "[N/A]" else None
                ),
                available=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None

    def _try_ollama_ps(self) -> Optional[GPUInfo]:
        """Attempt to infer VRAM usage from Ollama's running models."""
        try:
            result = subprocess.run(
                ["ollama", "ps"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return GPUInfo(
                    name="ollama",
                    vendor="unknown",
                    vram_total_bytes=16 * 1024 * 1024 * 1024,  # Assume 16 GB
                    vram_used_bytes=0,
                    vram_free_bytes=0,
                    available=True,
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None


class NoopGPUMonitor(GPUMonitor):
    """GPU monitor that returns empty data (for testing/CI)."""

    def _poll_now(self) -> GPUInfo:
        return GPUInfo(available=False)


# ── Helpers ─────────────────────────────────────────────────


def _find_int(data: dict, *keys: str) -> int:
    """Find the first matching key in a dict and return its int value."""
    for key in keys:
        if key in data:
            try:
                return int(data[key])
            except (ValueError, TypeError):
                pass
    return 0
