"""Runtime Recovery Engine (HOS-036).

Central engine that:
1. Listens to runtime events
2. Matches incidents to recovery policies
3. Executes recovery actions
4. Tracks history
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.runtime.recovery.recovery_actions import (
    RestartRuntimeAction,
    ReloadModelAction,
    SwitchRuntimeAction,
    UnloadResourceAction,
    NotifyAction,
)
from backend.runtime.recovery.recovery_models import (
    ActionType,
    RecoveryAttempt,
    RecoveryIncident,
    RecoveryPolicy,
    RecoveryStatus,
)
from backend.runtime.recovery.recovery_policy import RecoveryPolicyEngine


class RecoveryEngine:
    """Orchestrates incident detection and recovery execution.

    Thread-safe. Integrates with RuntimeEventBus via callback.
    """

    def __init__(
        self,
        policy_engine: Optional[RecoveryPolicyEngine] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._policy_engine = policy_engine or RecoveryPolicyEngine()
        self._on_event = on_event  # Callback for publishing recovery events

        # History tracking
        self._incidents: list[RecoveryIncident] = []
        self._attempts: dict[str, RecoveryAttempt] = {}
        self._attempt_counters: dict[str, dict[str, int]] = {}
        self._status: str = "healthy"

    # ── Event Listener ─────────────────────────────────────

    def on_runtime_event(self, event_type: str, runtime_id: str, payload: dict) -> None:
        """Handle a runtime event from the EventBus.

        This is the primary integration point with RuntimeEventBus.
        """
        incident = RecoveryIncident(
            incident_type=event_type,
            runtime_id=runtime_id,
            payload=payload,
        )

        with self._lock:
            self._incidents.append(incident)
            if len(self._incidents) > 1000:
                self._incidents = self._incidents[-1000:]

        # Match policies
        matches = self._policy_engine.match(incident)

        if not matches:
            return

        # Execute recovery
        for policy in matches:
            self._execute_policy(policy, incident)

    # ── Recovery Execution ─────────────────────────────────

    def _execute_policy(self, policy: RecoveryPolicy, incident: RecoveryIncident) -> None:
        """Execute all actions in a policy, tracking the attempt."""
        # Check attempt limits
        with self._lock:
            counter = self._attempt_counters.setdefault(policy.policy_id, {})
            counter.setdefault(incident.runtime_id, 0)
            if counter[incident.runtime_id] >= policy.max_attempts:
                return
            counter[incident.runtime_id] += 1

        # Create attempt
        attempt = RecoveryAttempt(
            incident_id=incident.incident_id,
            status=RecoveryStatus.IN_PROGRESS,
            actions=[self._bind_action(a, incident.runtime_id, incident.payload) for a in policy.actions],
            started_at=datetime.now(timezone.utc),
        )

        # Publish recovery.started
        if self._on_event:
            self._on_event(
                "recovery.started",
                {
                    "incident_id": incident.incident_id,
                    "policy": policy.name,
                    "runtime_id": incident.runtime_id,
                    "max_attempts": policy.max_attempts,
                },
                severity="info",
            )

        # Execute each action
        all_succeeded = True
        for action in attempt.actions:
            if self._on_event:
                self._on_event(
                    "recovery.action_started",
                    {
                        "action_type": action.action_type.value,
                        "runtime_id": action.runtime_id,
                    },
                    severity="info",
                )

            result = action.execute()
            attempt.results.append(result)

            if not result.success:
                all_succeeded = False
                break

        # Finalize
        attempt.status = RecoveryStatus.COMPLETED if all_succeeded else RecoveryStatus.FAILED
        attempt.completed_at = datetime.now(timezone.utc)

        with self._lock:
            self._attempts[attempt.attempt_id] = attempt

        # Publish result
        if self._on_event:
            event_type = "recovery.completed" if all_succeeded else "recovery.failed"
            self._on_event(
                event_type,
                {
                    "attempt_id": attempt.attempt_id,
                    "incident_id": incident.incident_id,
                    "status": attempt.status.value,
                    "actions_count": len(attempt.actions),
                    "duration_ms": (
                        (attempt.completed_at - attempt.started_at).total_seconds() * 1000
                        if attempt.completed_at and attempt.started_at
                        else 0
                    ),
                },
                severity="info" if all_succeeded else "error",
            )

        # Mark cooldown
        self._policy_engine.mark_cooldown(policy, incident.runtime_id)

    def _bind_action(self, action, runtime_id: str, payload: dict):
        """Clone an action with the runtime_id from the incident."""
        action_type = action.action_type
        if action_type == ActionType.RESTART_RUNTIME:
            return RestartRuntimeAction(runtime_id=runtime_id, **action.parameters)
        elif action_type == ActionType.RELOAD_MODEL:
            return ReloadModelAction(
                runtime_id=runtime_id,
                model_name=payload.get("model_name", action.parameters.get("model_name", "")),
            )
        elif action_type == ActionType.SWITCH_RUNTIME:
            return SwitchRuntimeAction(
                runtime_id=runtime_id,
                fallback_runtime=payload.get("fallback_runtime", action.parameters.get("fallback_runtime", "")),
            )
        elif action_type == ActionType.UNLOAD_RESOURCE:
            return UnloadResourceAction(runtime_id=runtime_id, **action.parameters)
        else:  # NOTIFY
            return NotifyAction(runtime_id=runtime_id, **action.parameters)

    # ── Query ───────────────────────────────────────────────

    def get_history(self, limit: int = 50) -> list[RecoveryAttempt]:
        """Return recent recovery attempts."""
        with self._lock:
            sorted_attempts = sorted(
                self._attempts.values(),
                key=lambda a: a.started_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return sorted_attempts[:limit]

    def get_status(self) -> dict:
        """Return engine status."""
        with self._lock:
            return {
                "status": self._status,
                "total_incidents": len(self._incidents),
                "total_attempts": len(self._attempts),
                "active_attempts": sum(
                    1 for a in self._attempts.values()
                    if a.status == RecoveryStatus.IN_PROGRESS
                ),
                "successful_attempts": sum(
                    1 for a in self._attempts.values()
                    if a.status == RecoveryStatus.COMPLETED
                ),
                "failed_attempts": sum(
                    1 for a in self._attempts.values()
                    if a.status == RecoveryStatus.FAILED
                ),
                "policies": len(self._policy_engine.list_policies()),
            }

    def retry_incident(self, incident_id: str) -> Optional[RecoveryAttempt]:
        """Manually retry a failed incident."""
        with self._lock:
            # Find the incident
            incident = None
            for inc in reversed(self._incidents):
                if inc.incident_id == incident_id:
                    incident = inc
                    break
            if incident is None:
                return None

        matches = self._policy_engine.match(incident)
        if matches:
            self._execute_policy(matches[0], incident)
            return self._attempts.get(
                incident_id, None
            )  # Returns the latest attempt for the incident
        return None
