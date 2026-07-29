"""Runtime Recovery Engine (HOS-036).

Auto-recovery layer that reacts to runtime incidents by executing
recovery policies with configurable actions (restart, reload, switch, unload, notify).
"""

from backend.runtime.recovery.recovery_models import (
    IncidentType,
    RecoveryIncident,
    RecoveryAttempt,
    RecoveryPolicy,
    RecoveryStatus,
    ActionType,
    ActionCost,
    RecoveryAction,
    ActionResult,
)
from backend.runtime.recovery.recovery_actions import (
    RestartRuntimeAction,
    ReloadModelAction,
    SwitchRuntimeAction,
    UnloadResourceAction,
    NotifyAction,
)
from backend.runtime.recovery.recovery_policy import RecoveryPolicyEngine
from backend.runtime.recovery.recovery_engine import RecoveryEngine

__all__ = [
    "IncidentType",
    "RecoveryIncident",
    "RecoveryAttempt",
    "RecoveryPolicy",
    "RecoveryStatus",
    "ActionType",
    "ActionCost",
    "RecoveryAction",
    "ActionResult",
    "RestartRuntimeAction",
    "ReloadModelAction",
    "SwitchRuntimeAction",
    "UnloadResourceAction",
    "NotifyAction",
    "RecoveryPolicyEngine",
    "RecoveryEngine",
]
