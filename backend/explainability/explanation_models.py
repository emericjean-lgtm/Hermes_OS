"""Explanation models for Hermes OS (HOS-064)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class DecisionType(str, Enum):
    AGENT_SELECTION = "agent_selection"
    RUNTIME_SELECTION = "runtime_selection"
    MODEL_SELECTION = "model_selection"
    TOOL_SELECTION = "tool_selection"
    SKILL_SELECTION = "skill_selection"
    WORKFLOW_DECISION = "workflow_decision"
    POLICY_DECISION = "policy_decision"
    SECURITY_DECISION = "security_decision"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DecisionAlternative:
    name: str
    reason: str
    score: float = 0.0
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)


@dataclass
class DecisionExplanation:
    decision_id: str
    decision_type: DecisionType
    decision: str
    reason: str
    confidence: float
    alternatives: list[DecisionAlternative] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    impact_description: str = ""
    rollback_possible: bool = True
    affected_components: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    description: str
    risk_level: RiskLevel
    impact: str
    affected_agents: list[str] = field(default_factory=list)
    rollback_possible: bool = True
    explanation: DecisionExplanation | None = None
    status: str = "pending"
    created_at: str = ""
    decided_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
