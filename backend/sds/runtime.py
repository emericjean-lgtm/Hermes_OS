"""SDS runtime — EventBusHolder and lifecycle helpers (HOS-003 / HOS-008).

This module provides the singleton pattern that bridges the abstract
EventBusInterface (HOS-001) and the concrete EventBusImpl (HOS-002)
into the FastAPI application lifecycle.

It also owns the module-level :class:`RuntimeRegistry` and
:class:`RuntimeFactory` singletons introduced by HOS-008.

.. note::
    ``EventBusHolder.install()`` accepts an ``EventBusImpl`` directly
    (not the bare ``EventBusInterface``) so it can call ``start()`` /
    ``stop()`` — both of which *are* part of the Protocol after the
    HOS-001 amendment, but which the holder nonetheless requires at
    construction time.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from backend.ral.event_bus import EventBusInterface
from backend.ral.event_bus_impl import EventBusImpl
from backend.ral.runtime_factory import RuntimeFactory, RuntimeLifecycle
from backend.ral.runtime_registry import RuntimeRegistry

if TYPE_CHECKING:
    # Imported for annotations only; RuntimeHolder.__init__ still imports it
    # lazily at call time to keep the module-level import graph acyclic.
    from backend.ral.runtime import RuntimeInterface

logger = logging.getLogger("hermes_os.sds.runtime")


class EventBusHolder:
    """Thread-safe singleton wrapper around the concrete ``EventBusImpl``.

    The holder does two things that the Protocol cannot express:
    * tracking ``started_at`` for uptime computation,
    * owning the concrete ``EventBusImpl`` instance.

    All other consumers should depend on ``get_eventbus()`` (which
    returns ``EventBusInterface``) rather than on this holder.
    """

    def __init__(self) -> None:
        self._bus: Optional[EventBusImpl] = None
        self._started_at: Optional[str] = None
        self._lock = threading.Lock()

    def install(self, bus: EventBusImpl) -> None:
        """Register the bus and record its boot timestamp."""
        with self._lock:
            self._bus = bus
            self._started_at = datetime.now(timezone.utc).isoformat()

    @property
    def bus(self) -> EventBusInterface:
        """Return the bus as a Protocol reference."""
        if self._bus is None:
            raise RuntimeError("eventbus_not_started")
        return self._bus

    @property
    def started_at(self) -> str:
        """ISO-8601 timestamp of when ``install()`` was called."""
        if self._started_at is None:
            raise RuntimeError("eventbus_not_started")
        return self._started_at

    @property
    def _bus_concrete(self) -> EventBusImpl:
        """Return the concrete instance (for ``stats()`` via D-23 cast)."""
        if self._bus is None:
            raise RuntimeError("eventbus_not_started")
        return self._bus

    async def stop(self) -> None:
        """Stop the bus and clear the holder state.

        The lock is released **before** the ``await`` to avoid holding
        a threading lock across an async boundary.
        """
        with self._lock:
            bus = self._bus
            self._bus = None
            self._started_at = None
        if bus is not None:
            await bus.stop()


# ------------------------------------------------------------------
# EventBusHolder — module-level singleton
# ------------------------------------------------------------------

_HOLDER: Optional[EventBusHolder] = None
_HOLDER_LOCK = threading.Lock()


def get_holder() -> EventBusHolder:
    """Return the module-level singleton ``EventBusHolder``."""
    global _HOLDER  # noqa: PLW0603
    if _HOLDER is not None:
        return _HOLDER
    with _HOLDER_LOCK:
        if _HOLDER is None:
            _HOLDER = EventBusHolder()
        return _HOLDER


async def init_eventbus_in_holder(sqlite_path: str) -> EventBusHolder:
    """Create, start, and install an ``EventBusImpl``.

    This is called from the FastAPI lifespan. It:

    1. Creates the parent directory (if missing).
    2. Instantiates ``EventBusImpl(sqlite_path)``.
    3. Calls ``await bus.start()``.
    4. Installs the bus into the module-level holder.
    """
    import os

    if sqlite_path and sqlite_path != ":memory:":
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)

    bus = EventBusImpl(sqlite_path=sqlite_path, retention_days=7)
    await bus.start()

    holder = get_holder()
    holder.install(bus)
    return holder


# ------------------------------------------------------------------
# RuntimeHolder — HOS-004
# ------------------------------------------------------------------


class RuntimeHolder:
    """Thread-safe singleton wrapper around a :class:`StubRuntime`.

    Follows the same pattern as ``EventBusHolder`` but for the active
    runtime adapter instance.
    """

    def __init__(self) -> None:
        from backend.ral.runtime import RuntimeInterface

        self._runtime: Optional[RuntimeInterface] = None
        self._lock = threading.Lock()

    def install(self, runtime: RuntimeInterface) -> None:
        """Register the runtime instance."""
        with self._lock:
            self._runtime = runtime

    @property
    def runtime(self) -> RuntimeInterface:
        """Return the registered runtime as a Protocol reference."""
        if self._runtime is None:
            raise RuntimeError("runtime_not_started")
        return self._runtime

    async def stop(self) -> None:
        """Stop the runtime and release the reference."""
        with self._lock:
            rt = self._runtime
            self._runtime = None
        if rt is not None:
            await rt.stop()


_RT_HOLDER: Optional[RuntimeHolder] = None
_RT_HOLDER_LOCK = threading.Lock()


def get_runtime_holder() -> RuntimeHolder:
    """Return the module-level singleton ``RuntimeHolder``."""
    global _RT_HOLDER  # noqa: PLW0603
    if _RT_HOLDER is not None:
        return _RT_HOLDER
    with _RT_HOLDER_LOCK:
        if _RT_HOLDER is None:
            _RT_HOLDER = RuntimeHolder()
        return _RT_HOLDER


async def init_stub_runtime_in_holder() -> RuntimeHolder:
    """Create, start, and install a ``StubRuntime``.

    The stub is injected with the already-initialised ``EventBusImpl``
    from the global holder so it can publish lifecycle events.

    .. note::
        Kept for HOS-004 compatibility. In HOS-008 it is superseded by
        :func:`init_runtime_registry_in_holder`.
    """
    from backend.ral.adapters.stub_runtime import StubRuntime

    bus = get_holder().bus
    stub = StubRuntime(bus=bus)
    await stub.start()

    holder = get_runtime_holder()
    holder.install(stub)
    return holder


# ------------------------------------------------------------------
# RuntimeRegistry / RuntimeFactory — HOS-008
# ------------------------------------------------------------------

_REGISTRY: Optional[RuntimeRegistry] = None
_FACTORY: Optional[RuntimeFactory] = None
_RTF_LOCK = threading.RLock()


def get_runtime_registry() -> RuntimeRegistry:
    """Return the module-level singleton ``RuntimeRegistry``."""
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is not None:
        return _REGISTRY
    with _RTF_LOCK:
        if _REGISTRY is None:
            _REGISTRY = RuntimeRegistry()
        return _REGISTRY


def get_runtime_factory() -> RuntimeFactory:
    """Return the module-level singleton ``RuntimeFactory``.

    The factory is wired to the module-level registry, so every runtime
    it creates is automatically registered.
    """
    global _FACTORY  # noqa: PLW0603
    if _FACTORY is not None:
        return _FACTORY
    with _RTF_LOCK:
        if _FACTORY is None:
            _FACTORY = RuntimeFactory(registry=get_runtime_registry())
        return _FACTORY


async def init_runtime_registry_in_holder(default_runtime: str = "stub") -> RuntimeHolder:
    """Bootstrap the runtime registry and wire it to the active holder.

    Steps:

    1. Register ``stub`` and ``ollama`` builders in the module-level
       :class:`RuntimeFactory`.
    2. Create the ``default_runtime`` instance, start it, and register
       it (done automatically by the factory).
    3. Point the legacy :class:`RuntimeHolder` at the default runtime so
       existing endpoints and tests keep working.

    Args:
        default_runtime: Name of the runtime to start by default.
            Defaults to ``"stub"`` to keep behaviour identical to
            HOS-004.

    Returns:
        The active :class:`RuntimeHolder`.
    """
    from backend.ral.adapters.hermes_ollama import HermesOllamaRuntime
    from backend.ral.adapters.stub_runtime import StubRuntime
    from backend.ral.runtime_config import RuntimeConfig
    from backend.connectors.ollama_client import OllamaClient

    factory = get_runtime_factory()
    bus = get_holder().bus

    # Register builders.  No network call is made here.
    factory.register_builder(
        "stub",
        lambda: StubRuntime(bus=bus),
    )
    factory.register_builder(
        "ollama",
        lambda config: HermesOllamaRuntime(
            config=config,
            ollama_client=OllamaClient(base_url=config.endpoint, timeout=config.timeout_seconds),
            event_bus=bus,
        ),
    )

    # Create and start the requested default runtime.
    if default_runtime == "stub":
        runtime = factory.create("stub")
    elif default_runtime == "ollama":
        default_config = RuntimeConfig(
            model="qwen3.5:9b",
            endpoint="http://127.0.0.1:11434",
            timeout_seconds=120,
        )
        runtime = factory.create("ollama", config=default_config)
    else:
        raise ValueError(f"Unknown default runtime '{default_runtime}'")

    await RuntimeLifecycle.initialize(runtime)

    holder = get_runtime_holder()
    holder.install(runtime)
    logger.info("Runtime registry initialized with default runtime '%s'", default_runtime)
    return holder


async def shutdown_runtime_registry() -> None:
    """Shut down every runtime registered in the module-level registry."""
    registry = get_runtime_registry()
    for name in registry.list_available():
        runtime = registry.get(name)
        try:
            await RuntimeLifecycle.shutdown(runtime)
        except Exception:  # pragma: no cover
            logger.warning("Failed to stop runtime '%s'", name, exc_info=True)
