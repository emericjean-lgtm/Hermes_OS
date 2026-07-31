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

from backend.runtime.resources.resource_models import GPUInfo


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
        """VRAM in use, as reported by Ollama, plus the adapter's real capacity.

        This used to shell out to ``ollama ps`` purely to decide whether a GPU
        existed, then report ``vram_total_bytes = 16 GiB  # Assume 16 GB`` and
        ``vram_used_bytes = 0`` — an invented capacity and a figure that was
        never measured. Both numbers now come from something that measured them:
        Ollama's own ``/api/ps`` reports ``size_vram`` per resident model, and
        the adapter's true capacity comes from :meth:`_adapter_vram_total`.
        """
        used = self._ollama_vram_used()
        if used is None:
            return None

        name, total = self._adapter_vram_total()
        return GPUInfo(
            name=name or "ollama",
            vendor="AMD" if name and "AMD" in name.upper() else "unknown",
            vram_total_bytes=total,
            vram_used_bytes=used,
            # Only meaningful when the capacity is known; 0 total would make
            # "free" a fabrication of the same kind this replaces.
            vram_free_bytes=max(total - used, 0) if total else 0,
            available=True,
        )

    @staticmethod
    def _ollama_vram_used() -> Optional[int]:
        """Sum ``size_vram`` over Ollama's resident models. None if unreachable.

        Returns 0 — not None — when Ollama answers with no model loaded: the
        runtime is present and using no VRAM, which is a measurement, not an
        absence of one.
        """
        import json
        import urllib.error
        import urllib.request

        endpoint = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        try:
            with urllib.request.urlopen(f"{endpoint}/api/ps", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return None

        models = payload.get("models")
        if not isinstance(models, list):
            return None
        return sum(int(m.get("size_vram", 0) or 0) for m in models)

    @staticmethod
    def _adapter_vram_total() -> tuple[str, int]:
        """The adapter's real VRAM capacity. ``("", 0)`` when undetectable.

        On Windows the driver publishes it as ``HardwareInformation.qwMemorySize``.
        WMI's ``Win32_VideoController.AdapterRAM`` is *not* used: it is a 32-bit
        field and reports 4 GiB for this 16 GiB card.
        """
        if os.name != "nt":
            return "", 0
        try:
            import winreg
        except ImportError:  # pragma: no cover - non-Windows
            return "", 0

        key_path = (r"SYSTEM\CurrentControlSet\Control\Class"
                    r"\{4d36e968-e325-11ce-bfc1-08002be10318}")
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
                for index in range(16):
                    try:
                        subkey_name = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, subkey_name) as sub:
                            size, _ = winreg.QueryValueEx(
                                sub, "HardwareInformation.qwMemorySize")
                            try:
                                desc, _ = winreg.QueryValueEx(sub, "DriverDesc")
                            except OSError:
                                desc = ""
                            if int(size) > 0:
                                return str(desc), int(size)
                    except OSError:
                        continue
        except OSError:
            pass
        return "", 0


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
