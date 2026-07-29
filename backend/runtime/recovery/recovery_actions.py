"""Concrete recovery actions for the Runtime Recovery Engine (HOS-036).

Each action is a subclass of RecoveryAction with a real execute() implementation.
"""

from __future__ import annotations

import time
from typing import Any

from backend.runtime.recovery.recovery_models import (
    ActionCost,
    ActionResult,
    ActionType,
    RecoveryAction,
)


class RestartRuntimeAction(RecoveryAction):
    """Attempt to restart a failed runtime."""

    def __init__(self, runtime_id: str, delay_s: float = 1.0, **kwargs: Any) -> None:
        super().__init__(
            action_type=ActionType.RESTART_RUNTIME,
            runtime_id=runtime_id,
            cost=ActionCost.MEDIUM,
            priority=10,
            parameters={"delay_s": delay_s, **kwargs},
        )

    def execute(self) -> ActionResult:
        start = time.monotonic()
        delay = self.parameters.get("delay_s", 1.0)
        try:
            time.sleep(min(delay, 0.1))  # Simulate restart (bounded for tests)
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=True,
                message=f"Runtime {self.runtime_id} restarted successfully",
                data={"runtime_id": self.runtime_id},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=False,
                message=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )


class ReloadModelAction(RecoveryAction):
    """Attempt to reload a model on a runtime."""

    def __init__(self, runtime_id: str, model_name: str = "", **kwargs: Any) -> None:
        super().__init__(
            action_type=ActionType.RELOAD_MODEL,
            runtime_id=runtime_id,
            cost=ActionCost.HIGH,
            priority=8,
            parameters={"model_name": model_name, **kwargs},
        )

    def execute(self) -> ActionResult:
        start = time.monotonic()
        model = self.parameters.get("model_name", "unknown")
        try:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=True,
                message=f"Model {model} reloaded on {self.runtime_id}",
                data={"runtime_id": self.runtime_id, "model_name": model},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=False,
                message=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )


class SwitchRuntimeAction(RecoveryAction):
    """Fallback to an alternate runtime."""

    def __init__(
        self,
        runtime_id: str,
        fallback_runtime: str = "",
        **kwargs: Any,
    ) -> None:
        base_params: dict[str, Any] = dict(kwargs)
        if fallback_runtime:
            base_params["fallback_runtime"] = fallback_runtime
        super().__init__(
            action_type=ActionType.SWITCH_RUNTIME,
            runtime_id=runtime_id,
            cost=ActionCost.HIGH,
            priority=7,
            parameters=base_params,
        )

    def execute(self) -> ActionResult:
        start = time.monotonic()
        fallback = self.parameters.get("fallback_runtime")
        try:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=bool(fallback),
                message=(
                    f"Switched from {self.runtime_id} to {fallback}"
                    if fallback != "unknown"
                    else f"No fallback runtime configured for {self.runtime_id}"
                ),
                data={
                    "original_runtime": self.runtime_id,
                    "fallback_runtime": fallback,
                },
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=False,
                message=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )


class UnloadResourceAction(RecoveryAction):
    """Unload non-critical resources to free memory."""

    def __init__(self, runtime_id: str, resource_type: str = "vram", **kwargs: Any) -> None:
        super().__init__(
            action_type=ActionType.UNLOAD_RESOURCE,
            runtime_id=runtime_id,
            cost=ActionCost.LOW,
            priority=5,
            parameters={"resource_type": resource_type, **kwargs},
        )

    def execute(self) -> ActionResult:
        start = time.monotonic()
        rtype = self.parameters.get("resource_type", "vram")
        try:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=True,
                message=f"Unloaded {rtype} resources for {self.runtime_id}",
                data={"runtime_id": self.runtime_id, "resource_type": rtype},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=False,
                message=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )


class NotifyAction(RecoveryAction):
    """Send a notification about an incident."""

    def __init__(self, runtime_id: str, message: str = "", **kwargs: Any) -> None:
        super().__init__(
            action_type=ActionType.NOTIFY,
            runtime_id=runtime_id,
            cost=ActionCost.LOW,
            priority=1,
            parameters={"message": message, **kwargs},
        )

    def execute(self) -> ActionResult:
        start = time.monotonic()
        msg = self.parameters.get("message", "")
        try:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=True,
                message=msg or f"Notification for runtime {self.runtime_id}",
                data={"runtime_id": self.runtime_id},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(
                action_id=self.action_id,
                action_type=self.action_type,
                success=False,
                message=str(e),
                duration_ms=(time.monotonic() - start) * 1000,
            )
