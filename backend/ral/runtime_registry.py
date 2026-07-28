"""Runtime Abstraction Layer — runtime registry (HOS-007).

Provides :class:`RuntimeRegistry`, a thread-safe, in-memory registry of
named runtime instances. The registry does **not** import any concrete
runtime adapter; it only manipulates :class:`RuntimeInterface` Protocol
references.
"""

from __future__ import annotations

import threading

from backend.ral.runtime import RuntimeInterface


class RuntimeRegistry:
    """Thread-safe registry of named :class:`RuntimeInterface` instances.

    The registry is intentionally lightweight: it stores runtime adapters
    by a human-readable identifier and provides synchronous lookup,
    listing, and removal operations. Lifecycle management is delegated to
    the runtimes themselves (through :meth:`RuntimeInterface.start` and
    :meth:`RuntimeInterface.stop`) or to :class:`RuntimeLifecycle` in
    ``backend.ral.runtime_factory``.

    Attributes:
        _runtimes: Internal mapping from runtime identifier to runtime.
        _lock: Threading lock protecting all accesses to ``_runtimes``.
    """

    def __init__(self) -> None:
        self._runtimes: dict[str, RuntimeInterface] = {}
        self._lock = threading.Lock()

    def register(self, name: str, runtime: RuntimeInterface) -> None:
        """Register ``runtime`` under ``name``.

        If ``name`` already exists, the previous runtime is overwritten.

        Args:
            name: Unique identifier for the runtime.
            runtime: Runtime instance to register.
        """
        with self._lock:
            self._runtimes[name] = runtime

    def get(self, name: str) -> RuntimeInterface:
        """Return the runtime registered under ``name``.

        Args:
            name: Runtime identifier.

        Returns:
            The registered runtime as a :class:`RuntimeInterface`.

        Raises:
            KeyError: If no runtime is registered under ``name``.
        """
        with self._lock:
            if name not in self._runtimes:
                raise KeyError(f"Runtime '{name}' is not registered.")
            return self._runtimes[name]

    def list_available(self) -> list[str]:
        """Return the list of registered runtime identifiers.

        Returns:
            A sorted list of runtime names.
        """
        with self._lock:
            return sorted(self._runtimes.keys())

    def remove(self, name: str) -> None:
        """Remove the runtime registered under ``name``.

        Args:
            name: Runtime identifier.

        Raises:
            KeyError: If no runtime is registered under ``name``.
        """
        with self._lock:
            if name not in self._runtimes:
                raise KeyError(f"Runtime '{name}' is not registered.")
            del self._runtimes[name]

    def find_name(self, runtime: RuntimeInterface) -> str | None:
        """Return the registry name of ``runtime`` by identity, or ``None``.

        This is useful when a consumer holds a runtime instance and needs
        to look up its health metrics or configuration by name.

        Args:
            runtime: Runtime instance to reverse-resolve.

        Returns:
            The registered name, or ``None`` if the instance is not
            registered.
        """
        with self._lock:
            for name, registered in self._runtimes.items():
                if registered is runtime:
                    return name
            return None
