"""Policy & Approval models for HOS-046."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DELEGATED = "delegated"
    CANCELLED = "cancelled"


class ApprovalPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class RuleCategory(str, Enum):
    SECURITY = "security"
    RESOURCE = "resource"
    OPERATION = "operation"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class AuditAction(str, Enum):
    EVALUATED = "evaluated"
    APPROVED = "approved"
    REJECTED = "rejected"
    DENIED = "denied"
    EXPIRED = "expired"
    DELEGATED = "delegated"


# ── Policy Rule ──────────────────────────────────────────────

@dataclass
class PolicyRule:
    """A configurable governance rule."""

    rule_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    category: RuleCategory = RuleCategory.CUSTOM
    # Condition (evaluated against context)
    condition: str = ""  # e.g. "operation == 'git_merge'" or "risk_level >= 8"
    decision: PolicyDecision = PolicyDecision.REVIEW_REQUIRED
    # Scope
    applies_to_all: bool = True
    mission_ids: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    # Config
    enabled: bool = True
    priority: int = 0  # higher = evaluated first
    require_approval_count: int = 1  # how many approvals needed
    auto_approve_if: str = ""  # condition for auto-approval
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Evaluation Context ───────────────────────────────────────

@dataclass
class EvaluationContext:
    """Context for policy evaluation."""

    context_id: str = field(default_factory=lambda: uuid4().hex)
    # What is being evaluated
    operation: str = ""  # e.g. "git_merge", "model_download", "workspace_delete"
    # Who
    agent_id: str = ""
    user_id: str = ""
    # Context
    mission_id: str = ""
    node_id: str = ""
    workspace_id: str = ""
    # Risk
    risk_level: float = 0.0  # 0-10
    # Details
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Evaluation Result ────────────────────────────────────────

@dataclass
class EvaluationResult:
    """Result of a policy evaluation."""

    result_id: str = field(default_factory=lambda: uuid4().hex)
    context: EvaluationContext = field(default_factory=EvaluationContext)
    decision: PolicyDecision = PolicyDecision.ALLOW
    matched_rules: list[str] = field(default_factory=list)  # rule IDs
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_id: str = ""
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Approval Request ─────────────────────────────────────────

@dataclass
class ApprovalRequest:
    """A human approval request."""

    approval_id: str = field(default_factory=lambda: uuid4().hex)
    # What needs approval
    operation: str = ""
    title: str = ""
    description: str = ""
    context: EvaluationContext = field(default_factory=EvaluationContext)
    # Who needs to approve
    required_approvals: int = 1
    approvers: list[str] = field(default_factory=list)  # agent/user IDs
    approved_by: list[str] = field(default_factory=list)
    rejected_by: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    # Status
    status: ApprovalStatus = ApprovalStatus.PENDING
    priority: ApprovalPriority = ApprovalPriority.NORMAL
    # Expiration
    timeout_seconds: float = 3600.0
    expires_at: Optional[datetime] = None
    # Delegation
    delegated_to: str = ""
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_resolved(self) -> bool:
        return self.status in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        )


# ── Audit Entry ──────────────────────────────────────────────

@dataclass
class AuditEntry:
    """A journaled governance decision."""

    audit_id: str = field(default_factory=lambda: uuid4().hex)
    action: AuditAction = AuditAction.EVALUATED
    # Who
    agent_id: str = ""
    user_id: str = ""
    # What
    operation: str = ""
    mission_id: str = ""
    node_id: str = ""
    # Result
    decision: str = ""
    reason: str = ""
    # Context
    details: dict[str, Any] = field(default_factory=dict)
    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
