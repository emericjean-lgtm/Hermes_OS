"""SDS route endpoints — public surface of Hermes OS (HOS-003 / HOS-008).

Routes exposed under ``/api/hermes-os/`` and the standalone liveness /
readiness endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.ral.event_bus import EventBusInterface
from backend.ral.event_bus_impl import EventBusImpl
from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_factory import RuntimeFactory, RuntimeLifecycle
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector, RuntimeSelectionError
from backend.sds.dependencies import (
    get_eventbus,
    get_runtime_context_dep,
    get_runtime_factory_dep,
    get_runtime_registry_dep,
)
from backend.sds.runtime import get_holder, get_runtime_holder

SDS_ROUTER = APIRouter(prefix="/api/hermes-os", tags=["hermes-os"])


@SDS_ROUTER.get("/health")
async def sds_health(
    bus: EventBusInterface = Depends(get_eventbus),
) -> dict:
    """Return the current health status of Hermes OS.

    Includes uptime and event-bus diagnostic counters.
    ``stats()`` is not part of ``EventBusInterface``, so we downcast
    per architecture decree D-23.
    """
    holder = get_holder()
    try:
        started = datetime.fromisoformat(holder.started_at)
        uptime = (datetime.now(timezone.utc) - started).total_seconds()
    except (RuntimeError, ValueError):
        uptime = 0.0

    # D-23: localised cast for the observability method.
    concrete = cast(EventBusImpl, bus)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "eventbus": concrete.stats(),
    }


# ------------------------------------------------------------------
# Liveness and readiness (k8s convention — D-21)
# ------------------------------------------------------------------


@SDS_ROUTER.get("/healthz", include_in_schema=False)
async def liveness() -> dict:
    """Kubernetes liveness probe: lightweight, no dependencies."""
    return {"alive": True}


@SDS_ROUTER.get("/readyz", include_in_schema=False)
async def readiness() -> dict:
    """Kubernetes readiness probe: verifies the bus is started."""
    holder = get_holder()
    try:
        _ = holder.bus
        return {"ready": True}
    except RuntimeError:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="eventbus_not_started")


# ------------------------------------------------------------------
# Runtime endpoint (HOS-004)
# ------------------------------------------------------------------


@SDS_ROUTER.get("/runtime")
async def runtime_info() -> dict:
    """Return metadata about the currently active runtime adapter."""
    from backend.sds.runtime import get_runtime_holder

    holder = get_runtime_holder()
    try:
        rt = holder.runtime
        return {
            "name": rt.name,
            "version": rt.version,
            "capabilities": list(rt.capabilities.available) if rt.capabilities else [],
            "started": True,
        }
    except RuntimeError:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="runtime_not_started")


# ------------------------------------------------------------------
# Runtime registry endpoints (HOS-008)
# ------------------------------------------------------------------


class _RuntimeSummary(BaseModel):
    name: str
    version: str
    capabilities: list[str]
    healthy: bool


class _RuntimeSelectResponse(BaseModel):
    selected: str
    previous: str | None


def _runtime_summary(
    name: str,
    rt: RuntimeInterface,
    *,
    active_name: str | None,
    fallback_name: str | None,
) -> dict:
    """Build a runtime summary dict used by ``list_runtimes`` and ``get_runtime``."""
    return {
        "name": name,
        "runtime_name": rt.name,
        "version": rt.version,
        "capabilities": list(rt.capabilities.available) if rt.capabilities else [],
        "healthy": RuntimeLifecycle.health_check(rt),
        "status": rt.status.value if rt.status else "unknown",
        "is_active": name == active_name,
        "is_fallback": name == fallback_name,
    }


@SDS_ROUTER.get("/runtimes")
async def list_runtimes(
    context: ActiveRuntimeContext = Depends(get_runtime_context_dep),
) -> dict:
    """List all registered runtime instances with active/fallback markers."""
    registry = context._registry
    active_name = context.get_active_name()
    fallback_name = context.fallback_name
    summaries = [
        _runtime_summary(
            name,
            registry.get(name),
            active_name=active_name,
            fallback_name=fallback_name,
        )
        for name in registry.list_available()
    ]
    return {
        "runtimes": summaries,
        "active": active_name,
        "fallback": fallback_name,
    }


@SDS_ROUTER.get("/runtimes/types")
async def list_runtime_types(
    factory: RuntimeFactory = Depends(get_runtime_factory_dep),
) -> dict:
    """List runtime types that can be instantiated by the factory."""
    return {"types": factory.available_types()}


@SDS_ROUTER.get("/runtimes/{name}")
async def get_runtime(
    name: str,
    registry: RuntimeRegistry = Depends(get_runtime_registry_dep),
) -> dict:
    """Return metadata for a registered runtime."""
    try:
        rt = registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _RuntimeSummary(
        name=rt.name,
        version=rt.version,
        capabilities=list(rt.capabilities.available) if rt.capabilities else [],
        healthy=RuntimeLifecycle.health_check(rt),
    ).model_dump()


@SDS_ROUTER.post("/runtimes/{name}/select")
async def select_runtime(
    name: str,
    context: ActiveRuntimeContext = Depends(get_runtime_context_dep),
) -> _RuntimeSelectResponse:
    """Switch the active runtime pointer to ``name``.

    The selected runtime must already be registered.  Future work may
    instantiate runtimes on demand through the factory.
    """
    previous_name = context.get_active_name()
    try:
        await RuntimeLifecycle.initialize(context.set_active(name))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _RuntimeSelectResponse(
        selected=name,
        previous=previous_name,
    )
