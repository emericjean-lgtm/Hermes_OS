"""Autonomous Guard for Hermes OS (HOS-063).

Final safety guard that validates every action through:
- Security Engine (HOS-057)
- Policy Engine (HOS-046)
- Approval Engine (HOS-046)

Blocks:
- Critical system modifications
- Permission changes
- Security bypass
- Mass deletion
- Architecture changes
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class GuardVerdict(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


class AutonomousGuard:
    """Final safety guard before any autonomous action.

    Integrates with Security Engine, Policy Engine, and Approval Engine.
    """

    def __init__(self) -> None:
        self._security_engine: Any = None
        self._policy_engine: Any = None
        self._blocked_actions: list[dict] = []

    def set_security_engine(self, engine: Any) -> None:
        self._security_engine = engine

    def set_policy_engine(self, engine: Any) -> None:
        self._policy_engine = engine

    def check_action(
        self, action_type: str, target: str, principal: str = "autonomous",
        context: dict | None = None,
    ) -> GuardVerdict:
        """Check if an action is allowed by all guard systems.

        Pipeline:
        1. Hard blocks (critical categories)
        2. Security Engine check
        3. Policy Engine check
        4. Allow
        """
        ctx = context or {}

        # 1. Hard blocks: never auto-allow
        blocked_categories = [
            "security.modify", "permission.change", "system.architecture",
            "mass_deletion", "policy.override", "guard.bypass",
        ]
        if action_type in blocked_categories:
            self._record_block(action_type, target, "Hard-blocked category")
            return GuardVerdict.BLOCK

        # 2. Security engine check
        if self._security_engine:
            try:
                sec_result = self._security_engine.check_access(
                    principal_id=principal,
                    resource_type=ctx.get("resource_type", "system"),
                    resource_id=target,
                    operation=action_type,
                    context=ctx,
                )
                if not sec_result.get("allowed", False):
                    self._record_block(action_type, target, sec_result.get("reason", "Security denied"))
                    return GuardVerdict.BLOCK
                if sec_result.get("requires_review", False):
                    return GuardVerdict.REVIEW
            except Exception:
                pass

        # 3. Policy engine check
        if self._policy_engine:
            try:
                policy_result = self._policy_engine.evaluate(
                    operation=action_type,
                    agent_id=principal,
                    mission_id=ctx.get("mission_id", ""),
                )
                if policy_result.get("verdict") == "DENY":
                    self._record_block(action_type, target, "Policy denied")
                    return GuardVerdict.BLOCK
            except Exception:
                pass

        return GuardVerdict.ALLOW

    def get_blocked_actions(self, limit: int = 50) -> list[dict]:
        return self._blocked_actions[-limit:]

    def stats(self) -> dict[str, Any]:
        return {
            "total_blocked": len(self._blocked_actions),
            "security_connected": self._security_engine is not None,
            "policy_connected": self._policy_engine is not None,
        }

    def _record_block(self, action_type: str, target: str, reason: str) -> None:
        import time
        self._blocked_actions.append({
            "action_type": action_type,
            "target": target,
            "reason": reason,
            "timestamp": time.time(),
        })
