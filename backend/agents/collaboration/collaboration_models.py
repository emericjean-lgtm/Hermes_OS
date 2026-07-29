"""Collaboration models for the Multi-Agent Collaboration Engine (HOS-044)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class MessageType(str, Enum):
    DIRECT = "direct"
    BROADCAST = "broadcast"
    GROUP = "group"
    HELP_REQUEST = "help_request"
    HELP_RESPONSE = "help_response"


class DelegationStatus(str, Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ConsensusStatus(str, Enum):
    PROPOSED = "proposed"
    VOTING = "voting"
    REACHED = "reached"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConsensusMode(str, Enum):
    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    SUPER_MAJORITY = "super_majority"  # 2/3
    SINGLE = "single"


class ConflictType(str, Enum):
    CONCURRENT_MODIFICATION = "concurrent_modification"
    DISAGREEMENT = "disagreement"
    RESOURCE_CONFLICT = "resource_conflict"
    DECISION_INCOMPATIBLE = "decision_incompatible"
    PRIORITY_CLASH = "priority_clash"


class ConflictStatus(str, Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    PROPOSED = "proposed"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ReviewStatus(str, Enum):
    REQUESTED = "requested"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


# ── Message ──────────────────────────────────────────────────

@dataclass
class AgentMessage:
    """A message between agents."""

    message_id: str = field(default_factory=lambda: uuid4().hex)
    sender_id: str = ""
    recipient_id: str = ""  # empty for broadcast
    type: MessageType = MessageType.DIRECT
    subject: str = ""
    body: str = ""
    # Threading
    conversation_id: str = ""
    reply_to: str = ""
    # Context
    mission_id: str = ""
    node_id: str = ""
    # Status
    read: bool = False
    acknowledged: bool = False
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    read_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Shared Context ───────────────────────────────────────────

@dataclass
class SharedContext:
    """Context shared between agents."""

    share_id: str = field(default_factory=lambda: uuid4().hex)
    owner_id: str = ""
    mission_id: str = ""
    # Content
    context_type: str = ""  # result, observation, decision, file
    title: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    # Permissions
    visible_to: list[str] = field(default_factory=list)  # empty = all
    editable_by: list[str] = field(default_factory=list)
    # Lifecycle
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Delegation ───────────────────────────────────────────────

@dataclass
class Delegation:
    """A task delegation from one agent to another."""

    delegation_id: str = field(default_factory=lambda: uuid4().hex)
    from_agent_id: str = ""
    to_agent_id: str = ""
    mission_id: str = ""
    node_id: str = ""
    # Request
    title: str = ""
    description: str = ""
    reason: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    # Context transfer
    shared_context_ids: list[str] = field(default_factory=list)
    # Status
    status: DelegationStatus = DelegationStatus.REQUESTED
    # Result
    result_summary: str = ""
    result_context_id: str = ""
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Review ───────────────────────────────────────────────────

@dataclass
class Review:
    """A cross-agent review request."""

    review_id: str = field(default_factory=lambda: uuid4().hex)
    requester_id: str = ""
    reviewer_id: str = ""  # empty = any available
    mission_id: str = ""
    node_id: str = ""
    # Content
    title: str = ""
    description: str = ""
    content_to_review: dict[str, Any] = field(default_factory=dict)
    # Status
    status: ReviewStatus = ReviewStatus.REQUESTED
    # Result
    verdict: str = ""  # approved, rejected, changes_requested
    comments: str = ""
    suggestions: list[str] = field(default_factory=list)
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Consensus ────────────────────────────────────────────────

@dataclass
class ConsensusProposal:
    """A proposal requiring consensus from multiple agents."""

    proposal_id: str = field(default_factory=lambda: uuid4().hex)
    proposer_id: str = ""
    mission_id: str = ""
    node_id: str = ""
    # Content
    title: str = ""
    description: str = ""
    options: list[str] = field(default_factory=list)
    # Configuration
    mode: ConsensusMode = ConsensusMode.MAJORITY
    minimum_voters: int = 2
    timeout_seconds: float = 300.0
    # Status
    status: ConsensusStatus = ConsensusStatus.PROPOSED
    # Votes
    votes: dict[str, str] = field(default_factory=dict)  # agent_id → option
    # Result
    winner: str = ""
    vote_count: dict[str, int] = field(default_factory=dict)
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def quorum_reached(self, total_voters: int) -> bool:
        return len(self.votes) >= self.minimum_voters

    def outcome(self) -> Optional[str]:
        if len(self.votes) < self.minimum_voters:
            return None
        counts: dict[str, int] = {}
        for option in self.votes.values():
            counts[option] = counts.get(option, 0) + 1

        total = len(self.votes)
        if self.mode == ConsensusMode.UNANIMOUS:
            return list(self.votes.values())[0] if len(set(self.votes.values())) == 1 and total >= self.minimum_voters else None
        elif self.mode == ConsensusMode.SUPER_MAJORITY:
            for opt, cnt in counts.items():
                if cnt / total >= 2 / 3:
                    return opt
            return None
        elif self.mode == ConsensusMode.MAJORITY:
            best = max(counts, key=counts.get)
            return best if counts[best] > total / 2 else None
        else:
            return list(self.votes.values())[0] if self.votes else None


# ── Conflict ─────────────────────────────────────────────────

@dataclass
class Conflict:
    """A detected conflict between agents."""

    conflict_id: str = field(default_factory=lambda: uuid4().hex)
    type: ConflictType = ConflictType.DISAGREEMENT
    status: ConflictStatus = ConflictStatus.DETECTED
    # Involved agents
    agent_ids: list[str] = field(default_factory=list)
    mission_id: str = ""
    node_id: str = ""
    # Content
    title: str = ""
    description: str = ""
    proposals: dict[str, str] = field(default_factory=dict)  # agent_id → proposed resolution
    # Resolution
    resolution: str = ""
    resolved_by: str = ""  # agent_id or "consensus" or "escalation"
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)
