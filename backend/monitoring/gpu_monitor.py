"""Hardware monitoring (cahier des charges §21): GPU VRAM/temperature/
load, loaded models via Ollama's own `/api/ps` (reused through
AgentRegistry's shared OllamaClient rather than opening a second
connection to the same server), CPU/RAM/swap, disk via stdlib.

Non-agent infrastructure, like MessageBus/WorkflowEngine/ProjectStore: no
LLM call is involved, so this isn't declared in config/agents.yaml —
reached via get_gpu_monitor() instead.

Two platform backends, picked via `platform.system()` (injectable as
`platform_name` for tests):

- **Linux**: `rocm-smi` for GPU, `/proc/meminfo` for RAM/swap,
  `os.getloadavg()` for CPU. Built and tested first, against the
  Ubuntu+ROCm target the cahier des charges assumes.
- **Windows**: confirmed necessary against real hardware — the actual
  target machine turned out to run Ollama natively on Windows, not
  Ubuntu+ROCm. No `rocm-smi` equivalent ships with Windows, so GPU VRAM
  comes from the registry (`HardwareInformation.qwMemorySize`, the
  usual trick since `Win32_VideoController.AdapterRAM` is capped at
  32-bit and misreports anything over ~4GB) and GPU load/dedicated
  memory from Windows' own cross-vendor `GPU Engine`/`GPU Adapter
  Memory` performance counters (built into Windows since 10 1809+, no
  vendor tool required) — both via PowerShell, already on every
  Windows machine. GPU **temperature** has no equivalent here: stock
  Windows exposes no cross-vendor thermal counter without a vendor
  tool (HWiNFO, AIDA64, ...) this project doesn't require installing,
  so `GpuStats.temp_c` is `None` on Windows rather than a misleading
  0.0 — alerts on it are simply skipped, never fabricated.

Every OS command is invoked through an injectable command runner rather
than shelling out directly, so tests can fake either platform's tools
without them actually being present. This sandbox has neither an AMD
GPU nor Windows (see README's "Important" note) — GpuMonitor.snapshot()
degrades gracefully to gpu=None whenever a command is missing or fails,
the same honesty this project has applied to every module built without
the real target hardware available. The Windows path in particular is
built from documented Windows APIs, not exercised end-to-end here —
verify it against a real machine before relying on its exact numbers.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.agent_registry import get_agent_registry
from backend.core.config import Settings, get_settings
from backend.runtime.resources import vram_physique


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
    # None on Windows: no cross-vendor thermal reading is available
    # without a vendor tool this project doesn't require (see module
    # docstring) — never fabricated as 0.0, which would misleadingly
    # read as "GPU is cold" rather than "not measured".
    temp_c: float | None
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
        platform_name: str = platform.system(),
    ) -> None:
        self._ollama = ollama_client
        self._settings = settings
        self._run_command = run_command
        self._disk_path = disk_path
        self._platform_name = platform_name

    async def snapshot(self) -> SystemSnapshot:
        # _read_gpu / _read_cpu_load / _read_memory are synchronous and, on
        # Windows, each shells out to one or more powershell.exe subprocesses
        # (up to six across the three calls, 5s timeout apiece). Calling them
        # directly here blocked the single asyncio event loop for as long as
        # those processes took — worst case 30s — which stalled every OTHER
        # in-flight request on this server too, not just this one. That is
        # what surfaced as a cascading httpx.ReadTimeout across unrelated
        # /api/v1/system/* routes once /status and /models became reachable
        # under /api/v1 (P-002). asyncio.to_thread moves the blocking work off
        # the loop; snapshot() still awaits it, so callers see no change.
        gpu = await asyncio.to_thread(self._read_gpu)
        loaded_models, ollama_alert = await self._read_loaded_models()
        cpu_load_pct = await asyncio.to_thread(self._read_cpu_load)
        ram_used_gb, ram_total_gb, swap_used_gb, swap_total_gb = await asyncio.to_thread(
            self._read_memory)
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
        if self._platform_name == "Windows":
            return self._read_gpu_windows()
        return self._read_gpu_linux()

    def _read_gpu_linux(self) -> GpuStats | None:
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

    def _read_gpu_windows(self) -> GpuStats | None:
        # Total VRAM: enumerate every GPU class registry subkey
        # (0000, 0001, ...) and take the largest qwMemorySize found —
        # Win32_VideoController.AdapterRAM is capped at 32-bit and
        # misreports anything over ~4GB, so this is the standard
        # workaround. Taking the max (not the first) matters on this
        # exact kind of machine: an i5-13500 has integrated graphics
        # (UHD 770) that can enumerate before a discrete RX 6800
        # depending on driver load order — the discrete card is
        # reliably the one with far more dedicated VRAM.
        total_output = self._run_command(
            [
                "powershell", "-NoProfile", "-Command",
                "0..9 | ForEach-Object { "
                "$p = \"HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
                "{4d36e968-e325-11ce-bfc1-08002be10318}\\000$_\"; "
                "if (Test-Path $p) { try { "
                "(Get-ItemProperty -Path $p -Name 'HardwareInformation.qwMemorySize' "
                "-ErrorAction Stop).'HardwareInformation.qwMemorySize' } catch {} } }",
            ]
        )
        if total_output is None:
            return None
        sizes = [self._parse_float(line) for line in total_output.splitlines()]
        sizes = [s for s in sizes if s is not None and s > 0]
        if not sizes:
            return None
        vram_total_gb = max(sizes) / 1e9

        # §6.2 / A-12 : **par processus, plus par adaptateur.**
        #
        # Le relevé de §6.2 annonçait un facteur trois — 3,99 Gio par
        # adaptateur contre 12,70 par processus. **Il ne se reproduit
        # pas** : remesuré trois fois de suite pendant A-15, carte chargée
        # d'un modèle de 12,74 Gio, l'adaptateur donne 14,669 Gio et les
        # processus 15,115, soit 0,445 Gio d'écart, stable. La sonde qui a
        # produit le 3,99 n'a pas été conservée et n'est plus auditable ;
        # le chiffre est donc retiré plutôt que répété.
        #
        # Ce qui reste vrai et mesuré : l'écart existe, il va toujours dans
        # le même sens — l'adaptateur sous-déclare — et le compteur par
        # processus est celui que `model_bench.gpu_dedicated_bytes` utilise
        # déjà. Le choix ne change pas ; son ampleur annoncée, si.
        #
        # Le compteur par processus est celui que
        # `model_bench.gpu_dedicated_bytes` utilise déjà, et celui que
        # `CLAUDE.md` désigne comme la seule occupation réelle — `/api/ps`
        # ne porte que les poids, ni le cache KV ni les tampons de calcul.
        #
        # GPU load + dedicated VRAM in use: Windows' own cross-vendor
        # performance counters (built in since Windows 10 1809, no
        # vendor tool needed). Summed across every adapter/process —
        # an approximation on a multi-GPU machine (iGPU + discrete),
        # but the iGPU's contribution is typically negligible next to
        # the discrete card's.
        # A-15 : la requete elle-meme vit dans
        # `runtime/resources/vram_physique.py` et nulle part ailleurs. Deux
        # ecritures de la meme question finissent par diverger — c'est
        # ainsi que le Cockpit et l'admission ont fini par lire deux
        # compteurs differents. Ici, seule la maniere d'executer la
        # commande change ; la question posee est la meme.
        occupation = vram_physique.occupation_physique_octets(
            executer=lambda requete: self._run_command(
                ["powershell", "-NoProfile", "-Command", requete]),
        )
        vram_used_gb = (occupation / 1e9) if occupation is not None else 0.0

        load_output = self._run_command(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' -ErrorAction Stop)"
                ".CounterSamples | Measure-Object -Property CookedValue -Sum "
                "| Select-Object -ExpandProperty Sum",
            ]
        )
        load_pct = min(100.0, self._parse_float(load_output) or 0.0) if load_output else 0.0

        return GpuStats(
            vram_used_gb=round(vram_used_gb, 2),
            vram_total_gb=round(vram_total_gb, 2),
            # No cross-vendor thermal counter ships with Windows — see
            # module docstring. Never fabricated as 0.0.
            temp_c=None,
            load_pct=round(load_pct, 1),
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

    @staticmethod
    def _parse_float(text: str | None) -> float | None:
        if text is None:
            return None
        try:
            return float(text.strip())
        except ValueError:
            return None

    def _read_cpu_load(self) -> float:
        if self._platform_name == "Windows":
            return self._read_cpu_load_windows()
        return self._read_cpu_load_linux()

    def _read_cpu_load_linux(self) -> float:
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

    def _read_cpu_load_windows(self) -> float:
        # Win32_Processor.LoadPercentage is an instantaneous 0-100
        # reading — no load-average-to-percentage conversion needed,
        # unlike the Linux path above.
        output = self._run_command(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_Processor | Measure-Object -Property "
                "LoadPercentage -Average -ErrorAction Stop).Average",
            ]
        )
        value = self._parse_float(output)
        return round(min(100.0, value), 1) if value is not None else 0.0

    def _read_memory(self) -> tuple[float, float, float, float]:
        if self._platform_name == "Windows":
            return self._read_memory_windows()
        return self._read_memory_linux()

    def _read_memory_linux(self) -> tuple[float, float, float, float]:
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

    def _read_memory_windows(self) -> tuple[float, float, float, float]:
        os_output = self._run_command(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_OperatingSystem | Select-Object "
                "TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress",
            ]
        )
        mem_total_gb = mem_used_gb = 0.0
        if os_output is not None:
            try:
                info = json.loads(os_output)
                total_kb = float(info["TotalVisibleMemorySize"])
                free_kb = float(info["FreePhysicalMemory"])
                mem_total_gb = total_kb / 1e6
                mem_used_gb = max(0.0, (total_kb - free_kb) / 1e6)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

        # Windows has no separate "swap" partition — the pagefile is its
        # closest equivalent, and Win32_PageFileUsage reports it in MB.
        # ConvertTo-Json gives a single object for one pagefile or a
        # list for several; handle both.
        pf_output = self._run_command(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_PageFileUsage | Select-Object "
                "AllocatedBaseSize,CurrentUsage | ConvertTo-Json -Compress",
            ]
        )
        swap_total_gb = swap_used_gb = 0.0
        if pf_output is not None:
            try:
                entries = json.loads(pf_output)
                if isinstance(entries, dict):
                    entries = [entries]
                swap_total_gb = sum(float(e["AllocatedBaseSize"]) for e in entries) / 1000
                swap_used_gb = sum(float(e["CurrentUsage"]) for e in entries) / 1000
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass

        return (
            round(mem_used_gb, 2),
            round(mem_total_gb, 2),
            round(swap_used_gb, 2),
            round(swap_total_gb, 2),
        )

    def _build_gpu_alerts(self, gpu: GpuStats | None) -> list[str]:
        if gpu is None:
            return []
        alerts = []
        # temp_c is None on platforms with no thermal reading available
        # (Windows — see module docstring); silently skip rather than
        # fabricate a comparison against a number that was never measured.
        if gpu.temp_c is not None:
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
