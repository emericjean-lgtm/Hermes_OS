"""Policy Engine — central governance orchestrator for HOS-046.

Centralizes all governance decisions: rules, approvals, and audit.
Integrates with all Hermes OS subsystems.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.policy.approval_engine import ApprovalEngine
from backend.policy.audit_log import AuditLog
from backend.policy.policy_models import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalStatus,
    AuditAction,
    AuditEntry,
    EvaluationContext,
    EvaluationResult,
    PolicyDecision,
)
from backend.policy.rule_evaluator import RuleEvaluator


class PolicyEngine:
    """Central governance engine.

    All sensitive operations must pass through this engine.
    Evaluates rules → approves/rejects → audits everything.

    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event

        # Subsystems
        self._evaluator = RuleEvaluator(on_event=on_event)
        self._approval = ApprovalEngine(on_event=on_event)
        self._audit = AuditLog(on_event=on_event)

    # ── Evaluate ─────────────────────────────────────────────

    def evaluate(
        self,
        operation: str,
        agent_id: str = "",
        user_id: str = "",
        mission_id: str = "",
        node_id: str = "",
        workspace_id: str = "",
        risk_level: float = 0.0,
        details: Optional[dict] = None,
    ) -> EvaluationResult:
        """Evaluate an operation against all governance rules.

        Returns the decision: ALLOW, DENY, or REVIEW_REQUIRED.
        If REVIEW_REQUIRED, an approval request is automatically created.
        """
        context = EvaluationContext(
            operation=operation,
            agent_id=agent_id,
            user_id=user_id,
            mission_id=mission_id,
            node_id=node_id,
            workspace_id=workspace_id,
            risk_level=risk_level,
            details=dict(details or {}),
        )

        # Evaluate rules
        decision, matched, reasons = self._evaluator.evaluate(context)

        result = EvaluationResult(
            context=context,
            decision=decision,
            matched_rules=matched,
            reasons=reasons,
        )

        # Auto-create approval if required
        if decision == PolicyDecision.REVIEW_REQUIRED:
            best_rule = self._evaluator.get_best_rule(context)
            req = self._approval.request_approval(
                operation=operation,
                title=f"Approval required: {operation}",
                description=f"Operation '{operation}' by agent '{agent_id}' requires approval.\n"
                           f"Reasons: {'; '.join(reasons)}",
                context=context,
                required_approvals=best_rule.require_approval_count if best_rule else 1,
                priority=ApprovalPriority.HIGH if risk_level >= 5 else ApprovalPriority.NORMAL,
            )
            result.requires_approval = True
            result.approval_id = req.approval_id

        # Audit
        start = datetime.now(timezone.utc)
        duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        self._audit.log(
            action=AuditAction.EVALUATED,
            agent_id=agent_id,
            operation=operation,
            mission_id=mission_id,
            decision=decision.value,
            reason="; ".join(reasons),
            duration_ms=duration_ms,
        )

        if self._on_event:
            ev = "policy.allowed" if decision == PolicyDecision.ALLOW else \
                 "policy.denied" if decision == PolicyDecision.DENY else \
                 "approval.requested"
            self._on_event(ev, {
                "operation": operation,
                "agent_id": agent_id,
                "decision": decision.value,
            }, severity="info" if decision == PolicyDecision.ALLOW else "warning")

        return result

    def is_allowed(
        self,
        operation: str,
        agent_id: str = "",
        risk_level: float = 0.0,
    ) -> bool:
        """Quick check: is this operation allowed?"""
        result = self.evaluate(operation=operation, agent_id=agent_id, risk_level=risk_level)
        return result.decision == PolicyDecision.ALLOW

    # ── Approval ─────────────────────────────────────────────

    def approve(
        self,
        approval_id: str,
        approver_id: str,
        comment: str = "",
    ) -> bool:
        """Approve a request."""
        ok = self._approval.approve(approval_id, approver_id, comment)
        if ok:
            req = self._approval.get(approval_id)
            if req and req.status == ApprovalStatus.APPROVED:
                self._audit.log(
                    AuditAction.APPROVED,
                    agent_id=approver_id,
                    operation=req.operation,
                    mission_id=req.context.mission_id,
                    decision="approved",
                    reason=comment,
                )
        return ok

    def reject(
        self,
        approval_id: str,
        rejecter_id: str,
        comment: str = "",
    ) -> bool:
        """Reject a request."""
        ok = self._approval.reject(approval_id, rejecter_id, comment)
        if ok:
            self._audit.log(
                AuditAction.REJECTED,
                agent_id=rejecter_id,
                decision="rejected",
                reason=comment,
            )
        return ok

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        return self._approval.get_pending()

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        return self._approval.get(approval_id)

    # ── Audit ────────────────────────────────────────────────

    def get_audit_log(
        self,
        agent_id: str = "",
        mission_id: str = "",
        operation: str = "",
        limit: int = 50,
    ) -> list[AuditEntry]:
        return self._audit.query(agent_id, mission_id, operation, limit=limit)

    def get_recent_audit(self, limit: int = 50) -> list[AuditEntry]:
        return self._audit.get_recent(limit)

    # ── Rules ────────────────────────────────────────────────

    def get_rules(self) -> list:
        rules = self._evaluator.get_all()
        return [
            {"id": r.rule_id, "name": r.name, "category": r.category.value,
             "decision": r.decision.value, "enabled": r.enabled, "priority": r.priority}
            for r in rules
        ]

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "rules": self._evaluator.stats(),
            "approvals": self._approval.stats(),
            "audit": self._audit.stats(),
        }

    # ── Properties ───────────────────────────────────────────

    @property
    def evaluator(self) -> RuleEvaluator:
        return self._evaluator

    @property
    def approval(self) -> ApprovalEngine:
        return self._approval

    @property
    def audit(self) -> AuditLog:
        return self._audit
