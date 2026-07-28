"""SDS dependencies — FastAPI ``Depends`` helpers (HOS-003 / HOS-008).

Every SDS route that needs the event bus uses ``Depends(get_eventbus)``,
which returns a typed ``EventBusInterface`` reference. If the bus has
not been started (e.g., the lifespan hasn't run yet), a 503 response is
returned.
"""
from __future__ import annotations

from fastapi import HTTPException

from backend.ral.event_bus import EventBusInterface
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_factory import RuntimeFactory
from backend.ral.runtime_registry import RuntimeRegistry
from backend.sds.runtime import get_holder, get_runtime_factory, get_runtime_registry, get_runtime_holder


async def get_eventbus() -> EventBusInterface:
    """FastAPI dependency — return the event bus instance.

    Raises:
        HTTPException 503: if the bus has not been initialized yet.
    """
    holder = get_holder()
    try:
        return holder.bus
    except RuntimeError:
        raise HTTPException(status_code=503, detail="eventbus_not_started")


def get_runtime_registry_dep() -> RuntimeRegistry:
    """FastAPI dependency — return the runtime registry instance.

    Raises:
        HTTPException 503: if the registry has not been initialized yet.
    """
    registry = get_runtime_registry()
    if not registry.list_available():
        raise HTTPException(status_code=503, detail="runtime_registry_not_initialized")
    return registry


def get_runtime_factory_dep() -> RuntimeFactory:
    """FastAPI dependency — return the runtime factory instance.

    Raises:
        HTTPException 503: if the factory has not been initialized yet.
    """
    factory = get_runtime_factory()
    if not factory.available_types():
        raise HTTPException(status_code=503, detail="runtime_factory_not_initialized")
    return factory


def get_runtime_context_dep() -> ActiveRuntimeContext:
    """FastAPI dependency — return the active runtime context.

    The context is built on demand from the module-level registry and
    holder singletons. It is stateless aside from the fallback pointer
    stored inside the context instance.

    Raises:
        HTTPException 503: if the runtime registry has not been
        initialized yet.
    """
    registry = get_runtime_registry()
    if not registry.list_available():
        raise HTTPException(status_code=503, detail="runtime_registry_not_initialized")
    return ActiveRuntimeContext(registry=registry, holder=get_runtime_holder())
