"""GET /system/status — hardware/process telemetry (cahier des charges
§21): which agents/models are configured, plus real GPU/CPU/RAM/disk
readings and currently-loaded Ollama models via monitoring/gpu_monitor.py.

GPU telemetry degrades to `"gpu": null` when `rocm-smi` isn't available
(no ROCm/AMD GPU on this machine — including this sandbox, see README's
"Important" note) rather than failing the whole endpoint; same for
loaded-model info if Ollama itself is unreachable (see GpuMonitor.snapshot).
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.agent_registry import get_agent_registry
from backend.core.config import load_models_config
from backend.monitoring.gpu_monitor import get_gpu_monitor

router = APIRouter()


@router.get("/system/status")
async def system_status() -> dict:
    registry = get_agent_registry()
    models_config = load_models_config()
    snapshot = await get_gpu_monitor().snapshot()
    return {
        "enabled_agents": registry.list_enabled(),
        "configured_roles": sorted(models_config["roles"]),
        **snapshot.to_dict(),
    }
