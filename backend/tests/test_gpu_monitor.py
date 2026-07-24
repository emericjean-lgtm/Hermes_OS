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
        fake_ollama_client, settings, run_command=lambda args: _ROCM_SMI_OUTPUT, disk_path=str(tmp_path)
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
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path))

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
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: hot_output, disk_path=str(tmp_path))

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
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: full_output, disk_path=str(tmp_path))

    snapshot = await monitor.snapshot()

    assert any("VRAM usage" in alert for alert in snapshot.alerts)


async def test_snapshot_reports_loaded_models_from_ollama_client(fake_ollama_client, tmp_path):
    fake_ollama_client._running = ["qwen3.5:9b"]
    settings = Settings()
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path))

    snapshot = await monitor.snapshot()

    assert snapshot.loaded_models == [{"name": "qwen3.5:9b"}]


async def test_snapshot_degrades_gracefully_when_ollama_unreachable(tmp_path):
    class BrokenOllamaClient:
        async def list_running_models(self):
            raise ConnectionError("no Ollama here")

    settings = Settings()
    monitor = GpuMonitor(BrokenOllamaClient(), settings, run_command=lambda args: None, disk_path=str(tmp_path))

    snapshot = await monitor.snapshot()

    assert snapshot.loaded_models == []
    assert any("unreachable" in alert for alert in snapshot.alerts)


async def test_snapshot_reports_disk_usage_for_given_path(fake_ollama_client, tmp_path):
    settings = Settings()
    monitor = GpuMonitor(fake_ollama_client, settings, run_command=lambda args: None, disk_path=str(tmp_path))

    snapshot = await monitor.snapshot()

    assert snapshot.disk_total_gb > 0
    assert snapshot.disk_free_gb >= 0
