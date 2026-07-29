"""FastAPI routes for the Runtime Resource Manager (HOS-035).

REST endpoints for resource status, allocations, and release.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.resources.resource_manager import ResourceManager
from backend.runtime.resources.resource_models import (
    ResourceAllocation,
    ResourceAllocationResult,
    ResourceType,
)

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
