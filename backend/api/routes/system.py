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


@router.get("/system/models")
async def system_models() -> dict:
    """The role → model table (§21) crossed with what Ollama is actually
    holding right now (§22).

    /system/status already reports `configured_roles`, but only as bare
    role *names* — which cannot answer the two questions that matter when
    a 16 GB budget is the constraint: which model does this role use, and
    is it resident? This joins config/models.yaml against Ollama's live
    list so `always_loaded` can be seen to be working (or not) rather
    than taken on trust.
    """
    config = load_models_config()
    # snapshot() is the monitor's public API; _read_loaded_models is
    # private and would couple this route to its internals.
    snapshot = await get_gpu_monitor().snapshot()
    loaded = {m.get("name", "") for m in snapshot.loaded_models}

    def _is_loaded(tag: str) -> bool:
        # Ollama reports "qwen3:1.7b" as "qwen3:1.7b" but a tagless
        # reference as "<name>:latest", so compare both ways rather than
        # reporting a resident model as absent on a naming technicality.
        return tag in loaded or f"{tag}:latest" in loaded

    roles = []
    for name, spec in (config.get("roles") or {}).items():
        tag = spec.get("model", "")
        roles.append(
            {
                "role": name,
                "model": tag,
                "tier": spec.get("tier", ""),
                "vram_gb": spec.get("vram_gb"),
                "always_loaded": bool(spec.get("always_loaded")),
                "loaded": _is_loaded(tag),
            }
        )

    roles.sort(key=lambda r: (not r["always_loaded"], not r["loaded"], r["role"]))
    return {
        "roles": roles,
        "loaded_count": len(loaded),
        "always_loaded_count": sum(1 for r in roles if r["always_loaded"]),
    }
