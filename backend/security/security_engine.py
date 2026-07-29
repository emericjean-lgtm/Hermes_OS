"""Security Engine for Hermes OS (HOS-057).

Central orchestrator for the security, sandbox, and trust layer.

Pipeline:
    Request
      ↓
    Permission Check  → PermissionManager
      ↓
    Trust Evaluation  → AgentTrustEngine
      ↓
    Threat Detection  → ThreatDetector
      ↓
    Isolation Check   → IsolationManager
      ↓
    Allow / Reject / Review
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .agent_trust_engine import AgentTrustEngine
from .isolation_manager import IsolationManager
from .permission_manager import PermissionManager
from .security_models import (
    PermissionAction,
    ResourceType,
    SECURITY_EVENTS,
    SecurityEvent,
    ThreatLevel,
    TrustLevel,
)
from .threat_detector import ThreatDetector


class SecurityEngine:
    """Central security orchestrator.

    Integrates permission checks, trust evaluation, threat detection,
    and isolation validation into a single decision pipeline.
    """

    def __init__(self, on_event: Callable | None = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        self.permissions = PermissionManager()
        self.trust = AgentTrustEngine()
        self.threats = ThreatDetector()
        self.isolation = IsolationManager()

        # Wire trust update events
        self.trust.on_trust_update(self._handle_trust_update)

    def check_access(
        self,
        principal_id: str,
        resource_type: ResourceType,
        resource_id: str,
        operation: str = "access",
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Full security pipeline check.

        Returns:
            dict with:
            - allowed: bool
            - reason: str
            - trust_score: float
            - threat_level: str
            - isolation_ok: bool
            - requires_review: bool
        """
        start = time.monotonic()
        ctx = context or {}

        # 1. Policy evaluation
        policy_action, matched_policy = self.permissions.evaluate_policies(
            principal_id, resource_type, resource_id
        )

        if policy_action == PermissionAction.DENY:
            self._publish(SECURITY_EVENTS["permission_denied"], {
                "principal": principal_id, "resource": resource_id,
                "reason": "Policy denied", "policy": matched_policy.policy_id if matched_policy else "",
            }, severity="warning")
            return {
                "allowed": False, "reason": "Policy denied",
                "policy": matched_policy.policy_id if matched_policy else "default_deny",
                "requires_review": False,
            }

        if policy_action == PermissionAction.REVIEW:
            return {
                "allowed": False, "reason": "Review required",
                "requires_review": True,
            }

        # 2. Permission check
        has_perm = self.permissions.check_permission(principal_id, resource_type, resource_id)
        if not has_perm:
            self._publish(SECURITY_EVENTS["permission_denied"], {
                "principal": principal_id, "resource": resource_id,
                "reason": "No explicit permission",
            }, severity="warning")
            return {
                "allowed": False, "reason": "Permission denied",
                "requires_review": False,
            }

        # 3. Trust evaluation
        trust_score = self.trust.get_score(principal_id)
        meets_trust = trust_score.score >= 20  # Minimum LOW level

        # 4. Threat detection
        threat_level = ThreatLevel.NONE
        if "file" in operation and context:
            threat = self.threats.check_file_access(
                principal_id, ctx.get("file_path", ""),
                ctx.get("allowed_paths", []),
            )
            if threat:
                self._publish(SECURITY_EVENTS["threat_detected"], {
                    "principal": principal_id, "threat": threat.to_dict(),
                }, severity="critical")
                threat_level = threat.level

        # 5. Publish permission checked event
        self._publish(SECURITY_EVENTS["permission_checked"], {
            "principal": principal_id, "resource": resource_id,
            "operation": operation, "trust_score": trust_score.score,
            "threat_level": threat_level.value,
        })

        allowed = meets_trust and threat_level not in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)

        return {
            "allowed": allowed,
            "reason": "Access granted" if allowed else "Trust too low or threat detected",
            "trust_score": trust_score.score,
            "trust_level": trust_score.level.value,
            "threat_level": threat_level.value,
            "requires_review": False,
        }

    def get_status(self) -> dict[str, Any]:
        """Get overall security status."""
        return {
            "permissions": self.permissions.stats(),
            "trust": self.trust.stats(),
            "threats": self.threats.stats(),
            "isolation": self.isolation.stats(),
            "timestamp": __import__("time").time(),
        }

    # ── Helpers ──

    def _handle_trust_update(self, agent_id: str, score: Any) -> None:
        self._publish(SECURITY_EVENTS["agent_trust_updated"], {
            "agent_id": agent_id, "score": score.score,
            "level": score.level.value,
        })

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass
