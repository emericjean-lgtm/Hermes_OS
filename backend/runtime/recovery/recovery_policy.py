"""Recovery Policy Engine (HOS-036).

Matches incidents to recovery rules and generates action plans.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from backend.runtime.recovery.recovery_actions import (
    NotifyAction,
    ReloadModelAction,
    RestartRuntimeAction,
    SwitchRuntimeAction,
    UnloadResourceAction,
)
from backend.runtime.recovery.recovery_models import (
    IncidentType,
    RecoveryIncident,
    RecoveryPolicy,
)


class RecoveryPolicyEngine:
    """Policy engine that matches incidents to recovery rules.

    Supports rule-based matching: when incident_type X, execute actions Y.
    """

    def __init__(self) -> None:
        self._policies: dict[str, RecoveryPolicy] = {}
        self._cooldowns: dict[str, dict[str, datetime]] = defaultdict(dict)
        self._load_default_policies()

    def _load_default_policies(self) -> None:
        """Register built-in recovery policies."""

        # Policy 1: Runtime failed → restart + notify
        self.add_policy(RecoveryPolicy(
            name="restart_on_failure",
            incident_types=[IncidentType.RUNTIME_FAILED.value],
            actions=[
                RestartRuntimeAction(runtime_id=""),
                NotifyAction(runtime_id="", message="Runtime failed — restart initiated"),
            ],
            max_attempts=3,
            cooldown_seconds=30.0,
            priority=10,
        ))

        # Policy 2: Runtime unavailable → switch runtime
        self.add_policy(RecoveryPolicy(
            name="fallback_on_unavailable",
            incident_types=[IncidentType.RUNTIME_UNAVAILABLE.value],
            actions=[
                SwitchRuntimeAction(runtime_id="", fallback_runtime=""),
                NotifyAction(runtime_id="", message="Runtime unavailable — fallback activated"),
            ],
            max_attempts=3,
            cooldown_seconds=60.0,
            priority=9,
        ))

        # Policy 3: Resource limit reached → unload non-critical
        self.add_policy(RecoveryPolicy(
            name="unload_on_resource_limit",
            incident_types=[IncidentType.RESOURCE_LIMIT_REACHED.value],
            actions=[
                UnloadResourceAction(runtime_id=""),
                NotifyAction(runtime_id="", message="Resource limit reached — unloading"),
            ],
            max_attempts=2,
            cooldown_seconds=15.0,
            priority=8,
        ))

        # Policy 4: Model load failed → reload model
        self.add_policy(RecoveryPolicy(
            name="reload_on_model_failure",
            incident_types=[IncidentType.MODEL_LOAD_FAILED.value],
            actions=[
                ReloadModelAction(runtime_id=""),
                NotifyAction(runtime_id="", message="Model load failed — reloading"),
            ],
            max_attempts=2,
            cooldown_seconds=20.0,
            priority=7,
        ))

        # Policy 5: Health degraded → notify
        self.add_policy(RecoveryPolicy(
            name="notify_on_health_degraded",
            incident_types=[IncidentType.HEALTH_DEGRADED.value],
            actions=[
                NotifyAction(runtime_id="", message="Runtime health degraded"),
            ],
            max_attempts=1,
            cooldown_seconds=60.0,
            priority=5,
        ))

        # Policy 6: Overloaded → unload resources
        self.add_policy(RecoveryPolicy(
            name="unload_on_overloaded",
            incident_types=[IncidentType.RUNTIME_OVERLOADED.value],
            actions=[
                UnloadResourceAction(runtime_id=""),
                NotifyAction(runtime_id="", message="Runtime overloaded — unloading"),
            ],
            max_attempts=2,
            cooldown_seconds=30.0,
            priority=6,
        ))

    # ── Policy Management ──────────────────────────────────

    def add_policy(self, policy: RecoveryPolicy) -> None:
        self._policies[policy.policy_id] = policy

    def remove_policy(self, policy_id: str) -> bool:
        return self._policies.pop(policy_id, None) is not None

    def list_policies(self) -> list[RecoveryPolicy]:
        return sorted(self._policies.values(), key=lambda p: p.priority, reverse=True)

    # ── Incident Matching ──────────────────────────────────

    def match(self, incident: RecoveryIncident) -> list[RecoveryPolicy]:
        """Return all policies that match the incident, respecting cooldowns."""
        matches: list[RecoveryPolicy] = []

        for policy in self._policies.values():
            if not policy.enabled:
                continue
            if incident.incident_type not in policy.incident_types:
                continue
            if self._in_cooldown(policy, incident.runtime_id):
                continue
            matches.append(policy)

        return sorted(matches, key=lambda p: p.priority, reverse=True)

    def _in_cooldown(self, policy: RecoveryPolicy, runtime_id: str) -> bool:
        """Check if a policy is in cooldown for a specific runtime."""
        last = self._cooldowns.get(policy.policy_id, {}).get(runtime_id)
        if last is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed < policy.cooldown_seconds

    def mark_cooldown(self, policy: RecoveryPolicy, runtime_id: str) -> None:
        """Record that a policy was triggered for a runtime."""
        self._cooldowns[policy.policy_id][runtime_id] = datetime.now(timezone.utc)
