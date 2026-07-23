"""GET /system/status — minimal stand-in for the full System view (§23.11).

The walking skeleton only reports which agents are enabled and which
models are configured; GPU/CPU/RAM telemetry (rocm-smi) is added once a
real GPU-equipped machine runs the backend (§21).
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.agent_registry import get_agent_registry
from backend.core.config import load_models_config

router = APIRouter()


@router.get("/system/status")
async def system_status() -> dict:
    registry = get_agent_registry()
    models_config = load_models_config()
    return {
        "enabled_agents": registry.list_enabled(),
        "configured_roles": sorted(models_config["roles"]),
        "gpu_monitor": "not available in this environment (no ROCm/rocm-smi)",
    }
