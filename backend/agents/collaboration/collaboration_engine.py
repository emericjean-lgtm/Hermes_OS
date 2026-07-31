"""Collaboration Engine — central orchestrator for HOS-044.

Coordinates all inter-agent collaboration: messaging, context sharing,
delegation, reviews, consensus, and conflict resolution.

Integrates with:
- AgentSupervisor (HOS-043): agent registry for message routing
- Mission Graph (HOS-041): mission/node context
- Event Bus (HOS-034): publishes collaboration events
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from backend.agents.collaboration.collaboration_models import (
    AgentMessage,
    Conflict,
    ConsensusMode,
    ConsensusProposal,
    ConflictType,
    Delegation,
    Review,
    ReviewStatus,
    SharedContext,
)
from backend.agents.collaboration.conflict_resolver import ConflictResolver
from backend.agents.collaboration.consensus_engine import ConsensusEngine
from backend.agents.collaboration.context_sharing import ContextSharing
from backend.agents.collaboration.delegation_manager import DelegationManager
from backend.agents.collaboration.message_bus import MessageBus


class CollaborationEngine:
    """Central collaboration engine for multi-agent coordination.

    Orchestrates all collaboration primitives:
    - MessageBus: inter-agent messaging
    - ContextSharing: shared context with permissions
    - DelegationManager: task delegation between agents
    - ConsensusEngine: voting-based consensus
    - ConflictResolver: detection and resolution of conflicts

    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.Lock()
        self._on_event = on_event

        # Subsystems
        self._messages = MessageBus(on_event=on_event)
        self._contexts = ContextSharing(on_event=on_event)
        self._delegations = DelegationManager(on_event=on_event)
        self._consensus = ConsensusEngine(on_event=on_event)
        self._conflicts = ConflictResolver(on_event=on_event)

        # Reviews (inline for simplicity)
        self._reviews: dict[str, Review] = {}

        if on_event:
            on_event("collaboration.started", {}, severity="info")

    # ── Messaging ────────────────────────────────────────────

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        subject: str,
        body: str,
        mission_id: str = "",
        node_id: str = "",
    ) -> AgentMessage:
        return self._messages.send(
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject=subject,
            body=body,
            mission_id=mission_id,
            node_id=node_id,
        )

    def broadcast_message(
        self, sender_id: str, subject: str, body: str, mission_id: str = ""
    ) -> AgentMessage:
        return self._messages.broadcast(sender_id, subject, body, mission_id)

    def request_help(
        self,
        sender_id: str,
        subject: str,
        body: str,
        required_capabilities: list[str],
        mission_id: str = "",
        node_id: str = "",
    ) -> AgentMessage:
        return self._messages.request_help(
            sender_id, subject, body, required_capabilities, mission_id, node_id
        )

    def get_inbox(self, agent_id: str) -> list[AgentMessage]:
        return self._messages.get_inbox(agent_id)

    def get_unread(self, agent_id: str) -> list[AgentMessage]:
        return self._messages.get_unread(agent_id)

    def get_conversation(self, conversation_id: str) -> list[AgentMessage]:
        return self._messages.get_conversation(conversation_id)

    # ── Context Sharing ──────────────────────────────────────

    def share_context(
        self, owner_id: str, mission_id: str, title: str, content: dict,
        context_type: str = "result", visible_to: Optional[list[str]] = None,
        editable_by: Optional[list[str]] = None,
    ) -> SharedContext:
        return self._contexts.share(
            owner_id, mission_id, title, content, context_type,
            visible_to, editable_by,
        )

    def get_shared_context(self, share_id: str, agent_id: str = "") -> Optional[SharedContext]:
        return self._contexts.get(share_id, agent_id)

    def get_visible_contexts(self, agent_id: str) -> list[SharedContext]:
        return self._contexts.get_visible_to(agent_id)

    # ── Delegation ───────────────────────────────────────────

    def delegate_task(
        self, from_id: str, to_id: str, mission_id: str, node_id: str,
        title: str, description: str = "", reason: str = "",
        required_capabilities: Optional[list[str]] = None,
    ) -> Delegation:
        return self._delegations.delegate(
            from_id, to_id, mission_id, node_id, title,
            description, reason, required_capabilities,
        )

    def accept_delegation(self, delegation_id: str, agent_id: str) -> bool:
        return self._delegations.accept(delegation_id, agent_id)

    def complete_delegation(self, delegation_id: str, agent_id: str, summary: str = "") -> bool:
        if not self._delegations.start(delegation_id, agent_id):
            return False
        return self._delegations.complete(delegation_id, agent_id, summary)

    def get_pending_delegations(self, agent_id: str) -> list[Delegation]:
        return self._delegations.get_pending(agent_id)

    # ── Reviews ──────────────────────────────────────────────

    def request_review(
        self, requester_id: str, reviewer_id: str, mission_id: str, node_id: str,
        title: str, content: dict, description: str = "",
    ) -> Review:
        r = Review(
            requester_id=requester_id,
            reviewer_id=reviewer_id,
            mission_id=mission_id,
            node_id=node_id,
            title=title,
            description=description,
            content_to_review=content,
        )
        with self._lock:
            self._reviews[r.review_id] = r

        if self._on_event:
            self._on_event("review.requested", {
                "review_id": r.review_id,
                "requester_id": requester_id,
                "reviewer_id": reviewer_id,
            }, severity="info")
        return r

    def submit_review(
        self, review_id: str, verdict: str, comments: str = "",
        suggestions: Optional[list[str]] = None,
    ) -> bool:
        with self._lock:
            r = self._reviews.get(review_id)
            if r is None:
                return False
            from datetime import datetime, timezone
            r.status = ReviewStatus(verdict) if verdict in [s.value for s in ReviewStatus] else ReviewStatus.APPROVED if verdict == "approved" else ReviewStatus.REJECTED
            r.verdict = verdict
            r.comments = comments
            r.suggestions = suggestions or []
            r.reviewed_at = datetime.now(timezone.utc)

        if self._on_event:
            self._on_event("review.completed", {
                "review_id": review_id,
                "verdict": verdict,
            }, severity="info")
        return True

    def get_review(self, review_id: str) -> Optional[Review]:
        return self._reviews.get(review_id)

    # ── Consensus ────────────────────────────────────────────

    def propose_consensus(
        self, proposer_id: str, mission_id: str, node_id: str,
        title: str, description: str, options: list[str],
        mode: ConsensusMode = ConsensusMode.MAJORITY,
        minimum_voters: int = 2,
    ) -> ConsensusProposal:
        p = self._consensus.propose(
            proposer_id, mission_id, node_id, title, description,
            options, mode, minimum_voters,
        )
        self._consensus.start_voting(p.proposal_id)
        return p

    def vote(self, proposal_id: str, agent_id: str, option: str) -> bool:
        return self._consensus.vote(proposal_id, agent_id, option)

    def get_consensus(self, proposal_id: str) -> Optional[ConsensusProposal]:
        return self._consensus.get(proposal_id)

    def get_active_proposals(self) -> list[ConsensusProposal]:
        return self._consensus.get_active()

    # ── Conflicts ────────────────────────────────────────────

    def report_conflict(
        self, conflict_type: ConflictType, agent_ids: list[str],
        mission_id: str, node_id: str, title: str, description: str,
    ) -> Conflict:
        return self._conflicts.detect(
            conflict_type, agent_ids, mission_id, node_id,
            title, description,
        )

    def resolve_conflict(
        self, conflict_id: str, resolution: str, resolved_by: str = "auto"
    ) -> bool:
        return self._conflicts.resolve(conflict_id, resolution, resolved_by)

    def auto_resolve_conflict(self, conflict_id: str) -> bool:
        return self._conflicts.auto_resolve(conflict_id)

    def get_active_conflicts(self) -> list[Conflict]:
        return self._conflicts.get_active()

    # ── Mission History ──────────────────────────────────────

    def get_mission_history(self, mission_id: str) -> dict[str, Any]:
        """Get complete collaboration history for a mission."""
        return {
            "mission_id": mission_id,
            "messages": [
                {"id": m.message_id, "from": m.sender_id, "to": m.recipient_id,
                 "type": m.type.value, "subject": m.subject}
                for m in self._messages.get_by_mission(mission_id)
            ],
            "contexts": [
                {"id": c.share_id, "owner": c.owner_id, "type": c.context_type,
                 "title": c.title}
                for c in self._contexts.get_by_mission(mission_id)
            ],
            "delegations": [
                {"id": d.delegation_id, "from": d.from_agent_id, "to": d.to_agent_id,
                 "status": d.status.value, "title": d.title}
                for d in self._delegations.get_by_mission(mission_id)
            ],
            "reviews": [
                {"id": r.review_id, "requester": r.requester_id,
                 "reviewer": r.reviewer_id, "status": r.status.value}
                for r in self._reviews.values() if r.mission_id == mission_id
            ],
            "consensus_proposals": [
                {"id": p.proposal_id, "proposer": p.proposer_id,
                 "status": p.status.value, "winner": p.winner}
                for p in self._consensus.get_by_mission(mission_id)
            ],
            "conflicts": [
                {"id": c.conflict_id, "type": c.type.value,
                 "status": c.status.value}
                for c in self._conflicts.get_by_mission(mission_id)
            ],
        }

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "messages": self._messages.stats(),
            "contexts": {"total": len(self._contexts._contexts)},
            "delegations": self._delegations.stats(),
            "consensus": self._consensus.stats(),
            "conflicts": self._conflicts.stats(),
            "reviews": {"total": len(self._reviews)},
        }

    # ── Properties ───────────────────────────────────────────

    @property
    def messages(self) -> MessageBus:
        return self._messages

    @property
    def contexts(self) -> ContextSharing:
        return self._contexts

    @property
    def delegations(self) -> DelegationManager:
        return self._delegations

    @property
    def consensus(self) -> ConsensusEngine:
        return self._consensus

    @property
    def conflicts(self) -> ConflictResolver:
        return self._conflicts
