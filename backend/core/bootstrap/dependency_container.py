"""Dependency container for Hermes OS (HOS-066B).

A single place that owns one instance of every subsystem.

Why a container and not module-level singletons: the subsystems were each
written with an injection seam already in place — most take ``on_event`` and
several route modules expose a ``create_*_routes(service)`` hook — but nothing
ever called those seams in production, so every subsystem either ran
unconfigured or answered 503. The container is what finally calls them, once,
from one place.

It deliberately does *not* do autowiring by type annotation. Specs declare
their dependencies by key (see :mod:`service_registry`), which keeps the graph
explicit and lets :class:`~backend.core.integration.dependency_graph.DependencyGraph`
validate it before anything is built.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Iterator, Optional, TypeVar

T = TypeVar("T")


class ContainerError(RuntimeError):
    """Raised when a container invariant is violated."""


class DuplicateServiceError(ContainerError):
    """Raised when a key is registered twice without ``replace=True``.

    This is the "one instance only" guarantee, enforced rather than assumed.
    """


class MissingServiceError(ContainerError):
    """Raised when an unregistered key is resolved."""


class DependencyContainer:
    """Thread-safe registry holding exactly one instance per service key."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._services: dict[str, Any] = {}
        self._order: list[str] = []

    # ── Registration ────────────────────────────────────────────────

    def register(self, key: str, instance: Any, *, replace: bool = False) -> Any:
        """Register ``instance`` under ``key`` and return it.

        Raises :class:`DuplicateServiceError` if the key is already taken and
        ``replace`` is False — a second instance of a subsystem is the exact
        failure mode this container exists to prevent.
        """
        if not key:
            raise ContainerError("service key must be a non-empty string")
        with self._lock:
            if key in self._services and not replace:
                raise DuplicateServiceError(
                    f"service {key!r} is already registered; "
                    "pass replace=True only if you really mean to swap it"
                )
            if key not in self._services:
                self._order.append(key)
            self._services[key] = instance
        return instance

    # ── Resolution ──────────────────────────────────────────────────

    def get(self, key: str) -> Any:
        with self._lock:
            try:
                return self._services[key]
            except KeyError:
                raise MissingServiceError(
                    f"service {key!r} is not registered "
                    f"(registered: {', '.join(sorted(self._services)) or 'none'})"
                ) from None

    def try_get(self, key: str, default: Optional[T] = None) -> Any:
        with self._lock:
            return self._services.get(key, default)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._services

    def require(self, *keys: str) -> tuple[Any, ...]:
        """Resolve several keys at once, failing on the first missing one."""
        return tuple(self.get(k) for k in keys)

    # ── Introspection ───────────────────────────────────────────────

    def keys(self) -> list[str]:
        """Registered keys in registration (dependency) order."""
        with self._lock:
            return list(self._order)

    def items(self) -> list[tuple[str, Any]]:
        with self._lock:
            return [(k, self._services[k]) for k in self._order]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.has(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._services)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DependencyContainer {len(self)} services>"

    # ── Teardown ────────────────────────────────────────────────────

    def clear(self) -> None:
        """Drop every reference. Used by tests and by shutdown."""
        with self._lock:
            self._services.clear()
            self._order.clear()

    def for_each_reversed(self, fn: Callable[[str, Any], None]) -> None:
        """Apply ``fn`` in reverse registration order.

        Shutdown runs backwards through the build order so a service is always
        torn down before the things it depends on.
        """
        for key in reversed(self.keys()):
            fn(key, self._services[key])
