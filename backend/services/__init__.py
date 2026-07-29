"""Hermes OS Service Layer (HOS-027).

This package contains the central facade — :class:`MissionControlService` —
which aggregates all Hermes OS kernel modules (HOS-009 through HOS-026)
into a single, unified API designed for consumption by the frontend,
REST/WebSocket APIs, integrations, and future distributed workers.

No business logic is duplicated; every method delegates to the
appropriate kernel module.
"""

from backend.services.mission_control import (
    MissionControlConfiguration,
    MissionControlError,
    MissionControlHealth,
    MissionControlService,
    MissionControlStatistics,
    MissionControlStatus,
)

__all__ = [
    "MissionControlConfiguration",
    "MissionControlError",
    "MissionControlHealth",
    "MissionControlService",
    "MissionControlStatistics",
    "MissionControlStatus",
]
