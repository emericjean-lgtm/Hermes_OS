"""Security models for Hermes OS (HOS-057)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Enums ──

class TrustLevel(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


class ResourceType(str, Enum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    WORKSPACE = "workspace"
    RUNTIME = "runtime"
    FILE = "file"
    NETWORK = "network"
    MEMORY = "memory"
    CONFIG = "config"


class IsolationLevel(str, Enum):
    NONE = "none"
    LOW = "low"        # Chroot-like
    MEDIUM = "medium"  # + network isolation
    HIGH = "high"      # + resource limits
    MAXIMUM = "maximum" # + no external access


# ── Data models ──

@dataclass
class SecurityPolicy:
    """A security policy definition."""
    policy_id: str = ""
    name: str = ""
    description: str = ""
    resource_type: ResourceType = ResourceType.AGENT
    action: PermissionAction = PermissionAction.ALLOW
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher = evaluated first
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "resource_type": self.resource_type.value,
            "action": self.action.value,
            "conditions": self.conditions,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Permission:
    """A permission grant for an agent/skill on a resource."""
    permission_id: str = ""
    principal_id: str = ""  # agent_id or skill_id
    resource_type: ResourceType = ResourceType.AGENT
    resource_id: str = ""
    allowed: bool = True
    granted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    granted_by: str = "system"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "permission_id": self.permission_id,
            "principal_id": self.principal_id,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "allowed": self.allowed,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "granted_by": self.granted_by,
        }


@dataclass
class CapabilityToken:
    """Short-lived token granting specific capabilities."""
    token_id: str = ""
    principal_id: str = ""
    capabilities: list[str] = field(default_factory=list)
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    ttl_seconds: int = 300
    scope: str = "task"

    def is_valid(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.now(timezone.utc) < self.expires_at

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "principal_id": self.principal_id,
            "capabilities": self.capabilities,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scope": self.scope,
        }


@dataclass
class AgentTrustScore:
    """Dynamic trust score for an agent."""
    agent_id: str = ""
    score: float = 50.0  # 0-100
    level: TrustLevel = TrustLevel.UNKNOWN
    total_tasks: int = 0
    success_count: int = 0
    failure_count: int = 0
    policy_violations: int = 0
    human_approvals: int = 0
    recent_behavior: float = 1.0  # Recent 10 tasks success rate
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "score": round(self.score, 1),
            "level": self.level.value,
            "total_tasks": self.total_tasks,
            "success_rate": round(self.success_count / max(self.total_tasks, 1) * 100, 1),
            "policy_violations": self.policy_violations,
            "human_approvals": self.human_approvals,
            "recent_behavior": round(self.recent_behavior, 2),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class SecurityEvent:
    """A security-relevant event."""
    event_id: str = ""
    event_type: str = ""
    source: str = ""
    severity: str = "info"
    principal_id: str = ""
    resource: str = ""
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "severity": self.severity,
            "principal_id": self.principal_id,
            "resource": self.resource,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ThreatDetection:
    """A detected threat."""
    threat_id: str = ""
    level: ThreatLevel = ThreatLevel.NONE
    source: str = ""
    principal_id: str = ""
    threat_type: str = ""
    description: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    severity_score: float = 0.0  # 0-1
    mitigated: bool = False
    mitigation_action: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    mitigated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "threat_id": self.threat_id,
            "level": self.level.value,
            "source": self.source,
            "principal_id": self.principal_id,
            "threat_type": self.threat_type,
            "description": self.description,
            "evidence": self.evidence,
            "severity_score": round(self.severity_score, 4),
            "mitigated": self.mitigated,
            "mitigation_action": self.mitigation_action,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class IsolationProfile:
    """Isolation configuration for a sandbox session."""
    profile_id: str = ""
    level: IsolationLevel = IsolationLevel.LOW
    allowed_files: list[str] = field(default_factory=list)
    allowed_networks: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    max_duration_s: int = 3600
    env_vars: dict[str, str] = field(default_factory=dict)
    read_only_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    network_blocked: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "level": self.level.value,
            "allowed_files": self.allowed_files,
            "network_blocked": self.network_blocked,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_percent": self.max_cpu_percent,
            "max_duration_s": self.max_duration_s,
            "allowed_tools": self.allowed_tools,
        }


# ── Event types ──

SECURITY_EVENTS = {
    "permission_checked": "security.permission.checked",
    "permission_denied": "security.permission.denied",
    "threat_detected": "security.threat.detected",
    "agent_trust_updated": "security.agent.trust.updated",
    "isolation_created": "security.isolation.created",
    "isolation_violation": "security.isolation.violation",
    "policy_updated": "security.policy.updated",
}
