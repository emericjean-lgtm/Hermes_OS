"""Runtime Abstraction Layer — core runtime contract.

This module defines the :class:`RuntimeInterface` contract that every
Hermes OS runtime adapter must satisfy. It intentionally contains **no
implementation**: concrete adapters live under
:mod:`backend.ral.adapters` and are introduced by HOS-005 and later.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from enum import Enum

if typing.TYPE_CHECKING:
    from backend.ral.capabilities import CapabilityInterface


@dataclass(frozen=True)
class CapabilitySet:
    """Immutable set of capability names advertised by a runtime.

    Attributes:
        available: frozenset of canonical capability names supported by the
            runtime. Values correspond to the ``name`` attribute of the
            capability protocols defined in :mod:`backend.ral.capabilities`.
    """

    available: frozenset[str]


class RuntimeStatus(str, Enum):
    """Lifecycle status of a runtime adapter."""

    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@typing.runtime_checkable
class RuntimeInterface(typing.Protocol):
    """Contract satisfied by every runtime that can be plugged into Hermes OS.

    A runtime is an abstraction over an agent execution engine (Hermes Agent,
    Claude Code, OpenCode, KTransformers, etc.). The rest of the system talks
    to the runtime only through this protocol and the capability protocols it
    exposes.

    Attributes:
        name: Canonical runtime identifier (e.g. ``"hermes-agent"``).
        version: Runtime adapter version string.
        capabilities: Capability set supported by this runtime.

    Notes:
        * The ``start`` / ``stop`` methods are async because adapters may
          launch external processes or connect to remote services.
        * ``get`` returns a capability instance only if the runtime actually
          supports the requested capability.
    """

    name: str
    version: str
    capabilities: CapabilitySet

    @property
    def status(self) -> RuntimeStatus:
        """Current lifecycle status of the runtime adapter.

        Must be one of :class:`RuntimeStatus` values. This makes the
        status accessible to any consumer typed with ``RuntimeInterface``
        without requiring a cast.
        """
        ...

    async def start(self) -> None:
        """Initialize the runtime and make it ready to accept work."""
        ...

    async def stop(self) -> None:
        """Release all runtime resources and stop any background activity."""
        ...

    def get(self, capability_name: str) -> CapabilityInterface | None:
        """Return the requested capability, or ``None`` if unsupported."""
        ...
