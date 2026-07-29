"""Freebuff Integration (HOS-026).

Provides a :class:`FreebuffAdapter` that bridges Hermes OS with Freebuff
for advanced planning, project management and development assistance.

Mapping Hermes OS → Freebuff:

    Hermes OS abstraction        →  Freebuff concept
    ────────────────────────────    ─────────────────────
    TaskMission / TaskPlan          Prompt generation
    MissionContext                  FreebuffProject
    UnifiedMemory                   Project memory sync
    Supervisor                      Project lifecycle
    SystemEventBus                  Event publishing
"""

from backend.integrations.freebuff.adapter import (
    FreebuffAdapter,
    FreebuffCapabilities,
    FreebuffConfiguration,
    FreebuffConnectionMode,
    FreebuffError,
    FreebuffProject,
    FreebuffPrompt,
    FreebuffResponse,
    FreebuffSession,
    FreebuffStatus,
)

__all__ = [
    "FreebuffAdapter",
    "FreebuffCapabilities",
    "FreebuffConfiguration",
    "FreebuffConnectionMode",
    "FreebuffError",
    "FreebuffProject",
    "FreebuffPrompt",
    "FreebuffResponse",
    "FreebuffSession",
    "FreebuffStatus",
]
