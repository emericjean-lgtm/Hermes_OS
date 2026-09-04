from __future__ import annotations

import json

import pytest

from backend.core.config import Settings
from backend.monitoring.gpu_monitor import GpuMonitor

pytestmark = pytest.mark.asyncio

_ROCM_SMI_OUTPUT = json.dumps(
    {
        "card0": {
            "Temperature (Sensor edge) (C)": "62.0",
            "GPU use (%)": "45",
            "VRAM Total Memory (B)": "17179869184",  # 16 GiB
            "VRAM Total Used Memory (B)": "8589934592",  # 8 GiB
        }
    }
)


async def test_snapshot_parses_rocm_smi_json(fake_ollama_client, tmp_path):
    settings = Settings(gpu_alert_temp_c=85, gpu_critical_temp_c=90, gpu_vram_warning_pct=85)
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=lambda args: _ROCM_SMI_OUTPUT, disk_path=str(tmp_path), platform_name="Linux"
    )

    snapshot = await monitor.snapshot()

    assert snapshot.gpu is not None
    assert snapshot.gpu.temp_c == 62.0
    assert snapshot.gpu.load_pct == 45.0
    assert snapshot.gpu.vram_total_gb == pytest.approx(17.18, abs=0.01)
    assert snapshot.gpu.vram_used_gb == pytest.approx(8.59, abs=0.01)
    assert snapshot.alerts == []


async def test_snapshot_gpu_is_none_when_rocm_smi_missing(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert snapshot.gpu is None
    assert snapshot.alerts == []


async def test_snapshot_raises_critical_temp_alert(fake_ollama_client, tmp_path):
    hot_output = json.dumps(
        {
            "card0": {
                "Temperature (Sensor edge) (C)": "92.0",
                "GPU use (%)": "99",
                "VRAM Total Memory (B)": "17179869184",
                "VRAM Total Used Memory (B)": "8589934592",
            }
        }
    )
    settings = Settings(gpu_critical_temp_c=90, gpu_alert_temp_c=85)
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: hot_output, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert any("critical threshold" in alert for alert in snapshot.alerts)


async def test_snapshot_raises_vram_warning_alert(fake_ollama_client, tmp_path):
    full_output = json.dumps(
        {
            "card0": {
                "Temperature (Sensor edge) (C)": "60.0",
                "GPU use (%)": "80",
                "VRAM Total Memory (B)": "17179869184",  # 16 GiB
                "VRAM Total Used Memory (B)": "16106127360",  # 15 GiB, ~93%
            }
        }
    )
    settings = Settings(gpu_vram_warning_pct=85, gpu_alert_temp_c=85, gpu_critical_temp_c=90)
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: full_output, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert any("VRAM usage" in alert for alert in snapshot.alerts)


async def test_snapshot_reports_loaded_models_from_ollama_client(fake_ollama_client, tmp_path):
    fake_ollama_client._running = ["qwen3.5:9b"]
    settings = Settings()
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert snapshot.loaded_models == [{"name": "qwen3.5:9b"}]


async def test_snapshot_degrades_gracefully_when_ollama_unreachable(tmp_path):
    class BrokenOllamaClient:
        async def list_running_models(self):
            raise ConnectionError("no Ollama here")

    settings = Settings()
    monitor = GpuMonitor(BrokenOllamaClient(), settings, run_command=lambda args: None, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert snapshot.loaded_models == []
    assert any("unreachable" in alert for alert in snapshot.alerts)


async def test_snapshot_reports_disk_usage_for_given_path(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path), platform_name="Linux")

    snapshot = await monitor.snapshot()

    assert snapshot.disk_total_gb > 0
    assert snapshot.disk_free_gb >= 0


# ── Windows platform backend ─────────────────────────────────────────────
# Same injectable-run_command approach as the Linux/rocm-smi tests above,
# but branching by command content since Windows needs several distinct
# PowerShell invocations (registry for total VRAM, two performance
# counters for GPU load/used VRAM, one for CPU, two for RAM/pagefile)
# rather than rocm-smi's single JSON blob.

_WIN_REGISTRY_VRAM = "16106127360\n536870912"  # 15 GiB (discrete) + 0.5 GiB (iGPU) — max wins
_WIN_GPU_USED = "8589934592"  # 8 GiB, bytes
_WIN_GPU_LOAD = "45"
_WIN_CPU_LOAD = "37"
_WIN_MEMINFO = json.dumps({"TotalVisibleMemorySize": 33554432, "FreePhysicalMemory": 16777216})  # KB, 32/16 GiB
_WIN_PAGEFILE = json.dumps({"AllocatedBaseSize": 4096, "CurrentUsage": 512})  # MB


def _windows_run_command(args: list[str]) -> str | None:
    script = args[-1]
    if "HardwareInformation.qwMemorySize" in script:
        return _WIN_REGISTRY_VRAM
    # §6.2 / A-12 : le compteur **par processus** remplace celui par
    # adaptateur, qui sous-déclarait d'un facteur trois — 3,99 Gio annoncés
    # quand les processus en détenaient 12,70 sur la même carte.
    if "GPU Process Memory" in script:
        return _WIN_GPU_USED
    if "GPU Adapter Memory" in script:
        raise AssertionError(
            "le compteur par adaptateur est de retour : il sous-déclare la "
            "VRAM réellement occupée")
    if "GPU Engine" in script:
        return _WIN_GPU_LOAD
    if "Win32_Processor" in script:
        return _WIN_CPU_LOAD
    if "Win32_OperatingSystem" in script:
        return _WIN_MEMINFO
    if "Win32_PageFileUsage" in script:
        return _WIN_PAGEFILE
    raise AssertionError(f"unexpected command in test: {script!r}")


async def test_snapshot_windows_parses_gpu_stats(fake_ollama_client, tmp_path):
    settings = Settings(gpu_alert_temp_c=85, gpu_critical_temp_c=90, gpu_vram_warning_pct=85)
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=_windows_run_command,
        disk_path=str(tmp_path), platform_name="Windows",
    )

    snapshot = await monitor.snapshot()

    assert snapshot.gpu is not None
    assert snapshot.gpu.vram_total_gb == pytest.approx(16.11, abs=0.01)  # max of the two sizes
    assert snapshot.gpu.vram_used_gb == pytest.approx(8.59, abs=0.01)
    assert snapshot.gpu.load_pct == 45.0
    assert snapshot.gpu.temp_c is None  # no cross-vendor thermal reading on Windows
    assert snapshot.alerts == []  # temp_c=None must never fabricate a threshold breach


async def test_snapshot_windows_gpu_is_none_when_registry_lookup_fails(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=lambda args: None,
        disk_path=str(tmp_path), platform_name="Windows",
    )

    snapshot = await monitor.snapshot()

    assert snapshot.gpu is None


async def test_snapshot_windows_cpu_and_memory(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=_windows_run_command,
        disk_path=str(tmp_path), platform_name="Windows",
    )

    snapshot = await monitor.snapshot()

    assert snapshot.cpu_load_pct == 37.0
    assert snapshot.ram_total_gb == pytest.approx(33.55, abs=0.01)
    assert snapshot.ram_used_gb == pytest.approx(16.78, abs=0.01)
    assert snapshot.swap_total_gb == pytest.approx(4.10, abs=0.01)
    assert snapshot.swap_used_gb == pytest.approx(0.51, abs=0.01)


async def test_snapshot_windows_memory_degrades_gracefully_when_commands_fail(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=lambda args: None,
        disk_path=str(tmp_path), platform_name="Windows",
    )

    snapshot = await monitor.snapshot()

    assert snapshot.cpu_load_pct == 0.0
    assert snapshot.ram_total_gb == 0.0
    assert snapshot.swap_total_gb == 0.0


async def test_snapshot_windows_never_raises_temperature_alert(fake_ollama_client, tmp_path):
    # Even with critical/alert thresholds set very low, temp_c=None must
    # never be compared against them — a fabricated 0.0 would otherwise
    # never breach either, masking the real "not measured" case.
    settings = Settings(gpu_alert_temp_c=1, gpu_critical_temp_c=2, gpu_vram_warning_pct=99)
    monitor = GpuMonitor(
        fake_ollama_client, settings, run_command=_windows_run_command,
        disk_path=str(tmp_path), platform_name="Windows",
    )

    snapshot = await monitor.snapshot()

    assert not any("temperature" in alert.lower() for alert in snapshot.alerts)
