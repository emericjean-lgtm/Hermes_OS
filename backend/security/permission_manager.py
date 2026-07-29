"""Permission Manager for Hermes OS (HOS-057).

Centralized permission management across agents, skills, tools,
workspace, and runtime resources.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from .security_models import (
    Permission,
    PermissionAction,
    ResourceType,
    SecurityPolicy,
)


class PermissionManager:
    """Manages permissions and policies for all resources.

    Thread-safe. Supports granting/revoking permissions and policy
    evaluation for agent → resource access.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._permissions: dict[str, Permission] = {}
        self._policies: dict[str, SecurityPolicy] = {}
        self._history: deque[dict] = deque(maxlen=500)

    def grant_permission(
        self,
        principal_id: str,
        resource_type: ResourceType,
        resource_id: str,
        allowed: bool = True,
        granted_by: str = "system",
        expires_at: Any = None,
    ) -> Permission:
        with self._lock:
            import uuid
            perm = Permission(
                permission_id=f"perm_{uuid.uuid4().hex[:8]}",
                principal_id=principal_id,
                resource_type=resource_type,
                resource_id=resource_id,
                allowed=allowed,
                granted_by=granted_by,
                expires_at=expires_at,
            )
            key = f"{principal_id}:{resource_type.value}:{resource_id}"
            self._permissions[key] = perm
            self._history.append({
                "action": "grant", "permission_id": perm.permission_id,
                "principal_id": principal_id, "resource": resource_id,
            })
            return perm

    def revoke_permission(self, principal_id: str, resource_type: ResourceType, resource_id: str) -> bool:
        with self._lock:
            key = f"{principal_id}:{resource_type.value}:{resource_id}"
            if key in self._permissions:
                del self._permissions[key]
                self._history.append({
                    "action": "revoke", "principal_id": principal_id,
                    "resource": resource_id,
                })
                return True
            return False

    def check_permission(
        self, principal_id: str, resource_type: ResourceType, resource_id: str
    ) -> bool:
        """Check if a principal has permission. Returns True if allowed."""
        with self._lock:
            key = f"{principal_id}:{resource_type.value}:{resource_id}"
            perm = self._permissions.get(key)
            if perm is None:
                return False
            if perm.is_expired():
                del self._permissions[key]
                return False
            return perm.allowed

    def list_permissions(self, principal_id: str | None = None) -> list[Permission]:
        with self._lock:
            perms = list(self._permissions.values())
            if principal_id:
                perms = [p for p in perms if p.principal_id == principal_id]
            return perms

    def add_policy(self, policy: SecurityPolicy) -> bool:
        with self._lock:
            if policy.policy_id in self._policies:
                return False
            self._policies[policy.policy_id] = policy
            return True

    def evaluate_policies(
        self, principal_id: str, resource_type: ResourceType, resource_id: str,
    ) -> tuple[PermissionAction, SecurityPolicy | None]:
        """Evaluate all policies for an access request.

        Returns (action, matched_policy). Policies are evaluated by
        priority (highest first). First match wins.
        """
        with self._lock:
            sorted_policies = sorted(
                [p for p in self._policies.values() if p.enabled],
                key=lambda p: p.priority, reverse=True,
            )
        for policy in sorted_policies:
            if policy.resource_type != resource_type:
                continue
            # Simple condition matching
            if policy.conditions:
                if "principal_id" in policy.conditions and policy.conditions["principal_id"] != principal_id:
                    continue
                if "resource_id" in policy.conditions and policy.conditions["resource_id"] != resource_id:
                    continue
            return policy.action, policy
        return PermissionAction.DENY, None

    def get_policies(self, resource_type: ResourceType | None = None) -> list[SecurityPolicy]:
        with self._lock:
            policies = list(self._policies.values())
            if resource_type:
                policies = [p for p in policies if p.resource_type == resource_type]
            return sorted(policies, key=lambda p: p.priority, reverse=True)

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._history)[-limit:]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_permissions": len(self._permissions),
                "total_policies": len(self._policies),
                "history_entries": len(self._history),
            }
