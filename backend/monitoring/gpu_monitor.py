"""Hardware monitoring (cahier des charges §21): GPU VRAM/temperature/
load via `rocm-smi`, loaded models via Ollama's own `/api/ps` (reused
through AgentRegistry's shared OllamaClient rather than opening a second
connection to the same server), CPU/RAM/swap via /proc, disk via stdlib.

Non-agent infrastructure, like MessageBus/WorkflowEngine/ProjectStore: no
LLM call is involved, so this isn't declared in config/agents.yaml —
reached via get_gpu_monitor() instead.

`rocm-smi` is invoked through an injectable command runner rather than
shelling out directly, so tests can fake a GPU-equipped machine without
one actually being present. This sandbox has none (see README's
"Important" note) — GpuMonitor.snapshot() degrades gracefully to
gpu=None when rocm-smi isn't on PATH or exits non-zero, the two ways of
saying "no AMD GPU here" (binary missing vs. no card/driver found), the
same honesty this project has applied to every other module built
without real hardware available.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.agent_registry import get_agent_registry
from backend.core.config import Settings, get_settings


class CommandRunner(Protocol):
    def __call__(self, args: list[str]) -> str | None: ...


def _run_command(args: list[str]) -> str | None:
    """Runs a command, returns stdout on success, None if the binary is
    missing or it fails — both just mean "no GPU telemetry available"."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


@dataclass
class GpuStats:
    vram_used_gb: float
    vram_total_gb: float
    temp_c: float
    load_pct: float


@dataclass
class SystemSnapshot:
    gpu: GpuStats | None
    loaded_models: list[dict]
    cpu_load_pct: float
    ram_used_gb: float
    ram_total_gb: float
    swap_used_gb: float
    swap_total_gb: float
    disk_free_gb: float
    disk_total_gb: float
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gpu": None
            if self.gpu is None
            else {
                "vram_used_gb": self.gpu.vram_used_gb,
                "vram_total_gb": self.gpu.vram_total_gb,
                "vram_used_pct": (
                    round(100 * self.gpu.vram_used_gb / self.gpu.vram_total_gb, 1)
                    if self.gpu.vram_total_gb
                    else 0.0
                ),
                "temp_c": self.gpu.temp_c,
                "load_pct": self.gpu.load_pct,
            },
            "loaded_models": self.loaded_models,
            "cpu_load_pct": self.cpu_load_pct,
            "ram_used_gb": self.ram_used_gb,
            "ram_total_gb": self.ram_total_gb,
            "swap_used_gb": self.swap_used_gb,
            "swap_total_gb": self.swap_total_gb,
            "disk_free_gb": self.disk_free_gb,
            "disk_total_gb": self.disk_total_gb,
            "alerts": self.alerts,
        }


class GpuMonitor:
    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        settings: Settings,
        *,
        run_command: CommandRunner = _run_command,
        disk_path: str = ".",
    ) -> None:
        self._ollama = ollama_client
        self._settings = settings
        self._run_command = run_command
        self._disk_path = disk_path

    async def snapshot(self) -> SystemSnapshot:
        gpu = self._read_gpu()
        loaded_models, ollama_alert = await self._read_loaded_models()
        cpu_load_pct = self._read_cpu_load()
        ram_used_gb, ram_total_gb, swap_used_gb, swap_total_gb = self._read_memory()
        disk = shutil.disk_usage(self._disk_path)

        alerts = self._build_gpu_alerts(gpu)
        if ollama_alert:
            alerts.append(ollama_alert)

        return SystemSnapshot(
            gpu=gpu,
            loaded_models=loaded_models,
            cpu_load_pct=cpu_load_pct,
            ram_used_gb=ram_used_gb,
            ram_total_gb=ram_total_gb,
            swap_used_gb=swap_used_gb,
            swap_total_gb=swap_total_gb,
            disk_free_gb=round(disk.free / 1e9, 2),
            disk_total_gb=round(disk.total / 1e9, 2),
            alerts=alerts,
        )

    async def _read_loaded_models(self) -> tuple[list[dict], str | None]:
        # A dashboard shouldn't 500 just because Ollama itself is down —
        # that's exactly the "Ollama down" case the cahier des charges'
        # error-handling section (§8.11) calls out, and this endpoint is
        # the natural place to surface it as status rather than a crash.
        try:
            return await self._ollama.list_running_models(), None
        except Exception:
            return [], "Ollama is unreachable — loaded-model info unavailable."

    def _read_gpu(self) -> GpuStats | None:
        output = self._run_command(
            ["rocm-smi", "--showtemp", "--showuse", "--showmeminfo", "vram", "--json"]
        )
        if output is None:
            return None
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return None
        # rocm-smi --json keys results by card id ("card0", "card1", ...);
        # this project targets a single discrete GPU, so take the first.
        card = next(iter(data.values()), None)
        if not card:
            return None
        try:
            vram_used_gb = float(card["VRAM Total Used Memory (B)"]) / 1e9
        except (KeyError, TypeError, ValueError):
            return None
        try:
            vram_total_gb = float(card["VRAM Total Memory (B)"]) / 1e9
        except (KeyError, TypeError, ValueError):
            # Fall back to the configured card size (.env's
            # GPU_VRAM_TOTAL_GB) rather than discarding a real reading —
            # ROCm's JSON keys have shifted across versions before.
            vram_total_gb = self._settings.gpu_vram_total_gb
        temp_c = self._first_float(
            card, ["Temperature (Sensor edge) (C)", "Temperature (Sensor junction) (C)"], default=0.0
        )
        load_pct = self._first_float(card, ["GPU use (%)"], default=0.0)
        return GpuStats(
            vram_used_gb=round(vram_used_gb, 2),
            vram_total_gb=round(vram_total_gb, 2),
            temp_c=temp_c,
            load_pct=load_pct,
        )

    @staticmethod
    def _first_float(card: dict, keys: list[str], *, default: float) -> float:
        for key in keys:
            if key in card:
                try:
                    return float(card[key])
                except (TypeError, ValueError):
                    continue
        return default

    def _read_cpu_load(self) -> float:
        # A 1-minute load average as a % of core count is a stateless
        # proxy for "how busy is the CPU" — unlike /proc/stat deltas, it
        # doesn't require keeping a sample from the previous call around,
        # which matters here since snapshot() is a one-shot poll, not a
        # running daemon with state between calls.
        try:
            load_1min = os.getloadavg()[0]
        except (OSError, AttributeError):
            return 0.0
        cpu_count = os.cpu_count() or 1
        return round(min(100.0, 100.0 * load_1min / cpu_count), 1)

    def _read_memory(self) -> tuple[float, float, float, float]:
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return 0.0, 0.0, 0.0, 0.0
        info: dict[str, int] = {}
        for line in lines:
            key, _, rest = line.partition(":")
            fields = rest.strip().split()
            if not fields:
                continue
            info[key] = int(fields[0])
        mem_total_gb = info.get("MemTotal", 0) / 1e6
        mem_available_gb = info.get("MemAvailable", 0) / 1e6
        swap_total_gb = info.get("SwapTotal", 0) / 1e6
        swap_free_gb = info.get("SwapFree", 0) / 1e6
        return (
            round(max(0.0, mem_total_gb - mem_available_gb), 2),
            round(mem_total_gb, 2),
            round(max(0.0, swap_total_gb - swap_free_gb), 2),
            round(swap_total_gb, 2),
        )

    def _build_gpu_alerts(self, gpu: GpuStats | None) -> list[str]:
        if gpu is None:
            return []
        alerts = []
        if gpu.temp_c >= self._settings.gpu_critical_temp_c:
            alerts.append(
                f"GPU temperature {gpu.temp_c:.0f}°C at or above the "
                f"critical threshold {self._settings.gpu_critical_temp_c:.0f}°C "
                "— consider pausing generation."
            )
        elif gpu.temp_c >= self._settings.gpu_alert_temp_c:
            alerts.append(
                f"GPU temperature {gpu.temp_c:.0f}°C at or above the "
                f"alert threshold {self._settings.gpu_alert_temp_c:.0f}°C."
            )
        if gpu.vram_total_gb:
            vram_pct = 100 * gpu.vram_used_gb / gpu.vram_total_gb
            if vram_pct >= self._settings.gpu_vram_warning_pct:
                alerts.append(
                    f"VRAM usage {vram_pct:.0f}% at or above the warning "
                    f"threshold {self._settings.gpu_vram_warning_pct:.0f}%."
                )
        return alerts


@lru_cache
def get_gpu_monitor() -> GpuMonitor:
    return GpuMonitor(get_agent_registry().ollama_client, get_settings())
