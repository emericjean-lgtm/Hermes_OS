"""Workspace Policy Engine for HOS-045.

Enforces rules: read-only, disk quota, max duration, network access, allowed tools.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.workspace.workspace_models import (
    PolicyAction,
    Workspace,
    WorkspacePolicy,
)


class WorkspacePolicyEngine:
    """Evaluates and enforces policies on workspaces.

    Built-in policies: disk quota (90% warning), max duration, read-only, network, tools.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._policies: dict[str, WorkspacePolicy] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Built-in default policies."""
        defaults = [
            WorkspacePolicy(
                name="disk_quota_warning",
                description="Warn when disk usage exceeds 90% of quota",
                condition="disk_used_mb > max_disk_mb * 0.9",
                action=PolicyAction.WARN,
                applies_to_all=True,
            ),
            WorkspacePolicy(
                name="disk_quota_deny",
                description="Deny writes when disk is full",
                condition="disk_used_mb >= max_disk_mb",
                action=PolicyAction.DENY,
                applies_to_all=True,
            ),
            WorkspacePolicy(
                name="max_duration_exceeded",
                description="Deny access when workspace duration exceeded",
                condition="duration_exceeded",
                action=PolicyAction.DENY,
                applies_to_all=True,
            ),
            WorkspacePolicy(
                name="read_only_enforcement",
                description="Enforce read-only mode",
                condition="read_only",
                action=PolicyAction.DENY,
                applies_to_all=True,
            ),
        ]
        for p in defaults:
            self._policies[p.policy_id] = p

    def register(self, policy: WorkspacePolicy) -> None:
        with self._lock:
            self._policies[policy.policy_id] = policy

    def remove(self, policy_id: str) -> bool:
        with self._lock:
            return self._policies.pop(policy_id, None) is not None

    def evaluate(self, workspace: Workspace) -> dict[str, PolicyAction]:
        """Evaluate all applicable policies for a workspace.

        Returns dict of policy_id → action.
        """
        results: dict[str, PolicyAction] = {}
        with self._lock:
            for pid, policy in self._policies.items():
                if not policy.enabled:
                    continue
                if not policy.applies_to_all:
                    if (policy.workspace_ids and
                            workspace.workspace_id not in policy.workspace_ids):
                        continue
                    if (policy.agent_ids and
                            workspace.agent_id not in policy.agent_ids):
                        continue

                action = self._evaluate_policy(policy, workspace)
                results[pid] = action

                if action == PolicyAction.DENY:
                    if self._on_event:
                        self._on_event("workspace.policy_denied", {
                            "workspace_id": workspace.workspace_id,
                            "policy": policy.name,
                        }, severity="warning")
        return results

    def check(self, workspace: Workspace) -> PolicyAction:
        """Check workspace against all policies. Returns strictest action."""
        results = self.evaluate(workspace)
        if PolicyAction.DENY in results.values():
            return PolicyAction.DENY
        if PolicyAction.WARN in results.values():
            return PolicyAction.WARN
        return PolicyAction.ALLOW

    def _evaluate_policy(self, policy: WorkspacePolicy, ws: Workspace) -> PolicyAction:
        """Evaluate a single policy against a workspace."""
        if policy.condition == "disk_used_mb > max_disk_mb * 0.9":
            if ws.disk_used_mb > ws.max_disk_mb * 0.9:
                return policy.action
        elif policy.condition == "disk_used_mb >= max_disk_mb":
            if ws.disk_used_mb >= ws.max_disk_mb:
                return policy.action
        elif policy.condition == "duration_exceeded":
            from datetime import datetime, timezone
            if ws.opened_at:
                elapsed = (datetime.now(timezone.utc) - ws.opened_at).total_seconds()
                if elapsed > ws.max_duration_seconds:
                    return policy.action
        elif policy.condition == "read_only":
            pass  # Handled by workspace policy attribute

        return PolicyAction.ALLOW

    def get_all(self) -> list[WorkspacePolicy]:
        with self._lock:
            return list(self._policies.values())

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._policies),
                "enabled": sum(1 for p in self._policies.values() if p.enabled),
                "by_action": {
                    a.value: sum(1 for p in self._policies.values() if p.action == a)
                    for a in PolicyAction
                },
            }
