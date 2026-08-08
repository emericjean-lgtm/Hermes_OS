"""FastAPI routes for the Runtime Resource Manager (HOS-035).

REST endpoints for resource status, allocations, and release.

``allocations``/``release`` (HOS-072 audit finding, documented rather than
silently left as-is): ``ResourceManager.reserve_resources()`` — the only
method that ever populates ``_allocations`` — is never called anywhere in
the real execution path. ``RealTaskExecutor._check_vram_admission`` only
calls the read-only ``can_allocate()`` before starting local inference; it
never commits a reservation. So ``GET /allocations`` is honestly always
empty and ``POST /release`` has nothing to release in a real deployment —
not a bug in these two endpoints themselves, but real callers should not
expect them to reflect actual VRAM usage. ``/loaded-models``/``/unload``
below are the real signal for "what's actually resident right now" instead
(Ollama's own ``/api/ps``).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from backend.runtime.resources.resource_manager import ResourceManager

router = APIRouter(prefix="/runtime/resources", tags=["runtime-resources"])

_manager: Optional[ResourceManager] = None


def create_resource_routes(manager: ResourceManager) -> APIRouter:
    """Factory: bind a ResourceManager to the routes."""
    global _manager
    _manager = manager
    return router


# ── REST Endpoints ─────────────────────────────────────────


@router.get("")
async def get_resources():
    """Get a comprehensive resource overview."""
    if _manager is None:
        return {"error": "ResourceManager not initialised"}

    return _manager.get_status()


@router.get("/status")
async def get_status():
    """Get resource health status."""
    if _manager is None:
        return {"error": "ResourceManager not initialised"}

    gpu = _manager.get_gpu_info()
    mem = _manager.get_memory_snapshot()
    thresholds = _manager.check_thresholds()

    return {
        "gpu_available": gpu.available,
        "gpu_name": gpu.name,
        "vram_usage_pct": (
            round(gpu.vram_used_bytes / max(gpu.vram_total_bytes, 1) * 100, 1)
        ),
        "ram_usage_pct": round(mem.usage_pct * 100, 1),
        "gpu_temperature": gpu.temperature_celsius,
        "active_alerts": [
            {"event_type": t, "severity": s} for t, s in thresholds
        ],
    }


@router.get("/allocations")
async def get_allocations():
    """List all active resource allocations."""
    if _manager is None:
        return {"allocations": [], "total_allocated_bytes": 0}

    allocs = _manager.get_current_allocations()
    return {
        "allocations": [
            {
                "id": a.allocation_id,
                "runtime_id": a.runtime_id,
                "resource_type": a.resource_type.value,
                "bytes_allocated": a.bytes_allocated,
                "model_name": a.model_name,
                "priority": a.priority,
                "created_at": a.created_at.isoformat(),
            }
            for a in allocs
        ],
        "total_allocated_bytes": sum(a.bytes_allocated for a in allocs),
        "count": len(allocs),
    }


@router.post("/release")
async def release_resources(allocation_id: str = Query(...)):
    """Release a specific resource allocation."""
    if _manager is None:
        return {"error": "ResourceManager not initialised"}

    released = _manager.release_resources(allocation_id)
    if released is None:
        return {"success": False, "reason": "Allocation not found or already released"}

    return {"success": True, "released_bytes": released, "allocation_id": allocation_id}


@router.get("/loaded-models")
async def get_loaded_models():
    """Real, currently-resident models — Ollama's own ``/api/ps`` (HOS-072).

    What the Runtime Center's "modèle actuellement chargé" panel actually
    needs: not the (always-empty, see module docstring) allocation
    bookkeeping, but what Ollama itself reports as loaded right now.
    """
    from backend.connectors.ollama_client import OllamaClient, OllamaUnavailableError
    from backend.core.config import get_settings

    settings = get_settings()
    client = OllamaClient(settings.ollama_api_url, timeout=10.0)
    try:
        models = await client.list_running_models()
    except OllamaUnavailableError as exc:
        return {"success": False, "error": str(exc), "models": []}
    finally:
        await client.aclose()

    return {
        "success": True,
        "models": [
            {
                "name": m.get("name") or m.get("model") or "",
                "size_bytes": int(m.get("size") or 0),
                "size_vram_bytes": int(m.get("size_vram") or 0),
                "expires_at": m.get("expires_at"),
            }
            for m in models
        ],
    }


@router.post("/unload")
async def unload_model(payload: dict[str, Any] = Body(...)):
    """Actively free a resident model's VRAM now (HOS-072) — the real
    backend for the Runtime Center's "décharger un modèle" action, instead
    of only ever waiting for Ollama's own keep_alive timer to expire.
    """
    model = str(payload.get("model") or "").strip()
    if not model:
        return {"success": False, "error": "model is required"}

    from backend.connectors.ollama_client import OllamaClient, OllamaUnavailableError
    from backend.core.config import get_settings

    settings = get_settings()
    client = OllamaClient(settings.ollama_api_url, timeout=15.0)
    try:
        await client.unload_model(model)
    except OllamaUnavailableError as exc:
        return {"success": False, "error": str(exc)}
    finally:
        await client.aclose()

    return {"success": True, "model": model}
