"""Hermes OS composition root (HOS-066B).

Turns the validated-but-unassembled subsystems into one running application.
See :mod:`backend.core.bootstrap.bootstrap` for the sequence and the reasoning.
"""

from backend.core.bootstrap.bootstrap import (
    BootstrapReport,
    HermesBootstrap,
    get_bootstrap,
    reset_bootstrap,
)
from backend.core.bootstrap.dependency_container import (
    ContainerError,
    DependencyContainer,
    DuplicateServiceError,
    MissingServiceError,
)
from backend.core.bootstrap.event_wiring import EventDispatcher, collect_known_topics
from backend.core.bootstrap.health import ServiceHealthProbe
from backend.core.bootstrap.service_registry import (
    SERVICE_SPECS,
    SPECS_BY_KEY,
    ServiceSpec,
    resolve_build_order,
)

__all__ = [
    "BootstrapReport",
    "ContainerError",
    "DependencyContainer",
    "DuplicateServiceError",
    "EventDispatcher",
    "HermesBootstrap",
    "MissingServiceError",
    "SERVICE_SPECS",
    "SPECS_BY_KEY",
    "ServiceHealthProbe",
    "ServiceSpec",
    "collect_known_topics",
    "get_bootstrap",
    "reset_bootstrap",
    "resolve_build_order",
]
