"""Runtime Abstraction Layer — active runtime context (HOS-009).

Provides :class:`ActiveRuntimeContext`, a thin, thread-safe abstraction
that sits on top of :class:`~backend.ral.runtime_registry.RuntimeRegistry`
and the legacy :class:`~backend.sds.runtime.RuntimeHolder`.

It is responsible for:

* remembering the currently **active** runtime,
* remembering a **fallback** runtime name,
* switching the active pointer safely,
* resolving the active runtime on demand.

The class intentionally contains **no business logic** about *which*
runtime should be active; that responsibility belongs to
:class:`~backend.ral.runtime_selector.RuntimeSelector`.
"""
from __future__ import annotations

import threading
from typing import Optional

from backend.ral.runtime import RuntimeInterface
from backend.ral.runtime_registry import RuntimeRegistry


class ActiveRuntimeContext:
    """Thread-safe manager for the active and fallback runtime pointers.

    Args:
        registry: Source of registered runtime instances.
        holder: The legacy runtime holder that stores the active runtime
            pointer. ``ActiveRuntimeContext`` writes into it; external
            callers can still read the active runtime through the holder.
    """

    def __init__(self, registry: RuntimeRegistry, holder: object) -> None:
        self._registry = registry
        self._holder = holder
        self._fallback_name: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def registry(self) -> RuntimeRegistry:
        """Return the registry backing this context."""
        return self._registry

    @property
    def active_runtime(self) -> RuntimeInterface:
        """Return the currently active runtime.

        Raises:
            RuntimeError: If no runtime has been activated yet.
        """
        return self._holder.runtime  # type: ignore[no-any-return]

    @property
    def fallback_name(self) -> Optional[str]:
        """Return the name of the current fallback runtime, if any."""
        with self._lock:
            return self._fallback_name

    def set_active(self, name: str) -> RuntimeInterface:
        """Switch the active runtime pointer to the runtime named ``name``.

        Args:
            name: Identifier of a runtime already present in the registry.

        Returns:
            The runtime instance that was activated.

        Raises:
            KeyError: If ``name`` is not registered.
            RuntimeError: If the selected runtime is not healthy and cannot
                be initialised.  This may be relaxed once automatic lifecycle
                management is added.
        """
        runtime = self._registry.get(name)

        with self._lock:
            self._holder.install(runtime)
            return runtime

    def set_fallback(self, name: Optional[str]) -> None:
        """Set the fallback runtime to ``name``.

        The fallback is stored as a name rather than an instance so it can
        be re-resolved lazily when needed.

        Args:
            name: Identifier of a runtime in the registry, or ``None`` to
                clear the fallback.

        Raises:
            KeyError: If ``name`` is not registered.
        """
        with self._lock:
            if name is not None:
                # Eager validation: the fallback must point to a registered
                # runtime.  We read but do not store the instance.
                _ = self._registry.get(name)
            self._fallback_name = name

    def get_active_name(self) -> Optional[str]:
        """Return the registry name of the active runtime, if known.

        The active pointer is stored as an runtime instance inside the
        holder, so we reverse-resolve it by comparing the instance identity
        with the registered instances.  If the active runtime was installed
        directly into the holder (legacy path) without going through the
        registry, this method returns ``None``.
        """
        try:
            active = self._holder.runtime
        except RuntimeError:
            return None

        with self._lock:
            for name, runtime in _registry_entries(self._registry):
                if runtime is active:
                    return name
            return None


def _registry_entries(registry: RuntimeRegistry) -> list[tuple[str, RuntimeInterface]]:
    """Return (name, runtime) pairs from *registry* without exposing internals."""
    return [(name, registry.get(name)) for name in registry.list_available()]
