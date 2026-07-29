"""Consensus Engine for the Multi-Agent Collaboration Engine (HOS-044).

Supports voting-based consensus: unanimous, majority, super-majority, single.
Configurable minimum voters and timeouts.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.collaboration.collaboration_models import (
    ConsensusMode,
    ConsensusProposal,
    ConsensusStatus,
)


class ConsensusEngine:
    """Manages consensus proposals and voting.

    Supports unanimous, majority (50%+1), super-majority (2/3), and single-voter modes.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._proposals: dict[str, ConsensusProposal] = {}
        self._by_mission: dict[str, list[str]] = {}

    def propose(
        self,
        proposer_id: str,
        mission_id: str,
        node_id: str,
        title: str,
        description: str,
        options: list[str],
        mode: ConsensusMode = ConsensusMode.MAJORITY,
        minimum_voters: int = 2,
        timeout_seconds: float = 300.0,
    ) -> ConsensusProposal:
        """Create a consensus proposal."""
        p = ConsensusProposal(
            proposer_id=proposer_id,
            mission_id=mission_id,
            node_id=node_id,
            title=title,
            description=description,
            options=list(options),
            mode=mode,
            minimum_voters=minimum_voters,
            timeout_seconds=timeout_seconds,
        )
        with self._lock:
            self._proposals[p.proposal_id] = p
            self._by_mission.setdefault(mission_id, []).append(p.proposal_id)

        if self._on_event:
            self._on_event("consensus.started", {
                "proposal_id": p.proposal_id,
                "proposer_id": proposer_id,
                "mode": mode.value,
                "options": options,
            }, severity="info")
        return p

    def start_voting(self, proposal_id: str) -> bool:
        """Open voting on a proposal."""
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None or p.status != ConsensusStatus.PROPOSED:
                return False
            p.status = ConsensusStatus.VOTING
        return True

    def vote(self, proposal_id: str, agent_id: str, option: str) -> bool:
        """Cast a vote on a proposal."""
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None or p.status not in (ConsensusStatus.PROPOSED, ConsensusStatus.VOTING):
                return False
            if option not in p.options:
                return False

            p.status = ConsensusStatus.VOTING
            p.votes[agent_id] = option
            p.vote_count = {}
            for o in p.votes.values():
                p.vote_count[o] = p.vote_count.get(o, 0) + 1

        # Check if consensus reached
        outcome = p.outcome()
        if outcome is not None:
            with self._lock:
                p.status = ConsensusStatus.REACHED
                p.winner = outcome
                p.resolved_at = datetime.now(timezone.utc)

            if self._on_event:
                self._on_event("consensus.reached", {
                    "proposal_id": proposal_id,
                    "winner": outcome,
                    "votes": dict(p.votes),
                    "mode": p.mode.value,
                }, severity="info")
        return True

    def try_resolve(self, proposal_id: str) -> Optional[str]:
        """Check if consensus can be resolved now. Returns winner or None."""
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None or p.status == ConsensusStatus.REACHED:
                return p.winner if p else None

            outcome = p.outcome()
            if outcome is not None:
                p.status = ConsensusStatus.REACHED
                p.winner = outcome
                p.resolved_at = datetime.now(timezone.utc)

                if self._on_event:
                    self._on_event("consensus.reached", {
                        "proposal_id": proposal_id,
                        "winner": outcome,
                        "votes": dict(p.votes),
                        "mode": p.mode.value,
                    }, severity="info")
            return outcome

    def cancel(self, proposal_id: str) -> bool:
        with self._lock:
            p = self._proposals.get(proposal_id)
            if p is None or p.status in (ConsensusStatus.REACHED, ConsensusStatus.CANCELLED):
                return False
            p.status = ConsensusStatus.CANCELLED
        return True

    # ── Query ────────────────────────────────────────────────

    def get(self, proposal_id: str) -> Optional[ConsensusProposal]:
        return self._proposals.get(proposal_id)

    def get_by_mission(self, mission_id: str) -> list[ConsensusProposal]:
        with self._lock:
            ids = self._by_mission.get(mission_id, [])
            return [self._proposals[pid] for pid in ids if pid in self._proposals]

    def get_active(self) -> list[ConsensusProposal]:
        with self._lock:
            return [p for p in self._proposals.values()
                    if p.status in (ConsensusStatus.PROPOSED, ConsensusStatus.VOTING)]

    def get_resolved(self) -> list[ConsensusProposal]:
        with self._lock:
            return [p for p in self._proposals.values()
                    if p.status == ConsensusStatus.REACHED]

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._proposals),
                "active": len(self.get_active()),
                "resolved": len(self.get_resolved()),
                "by_mode": {
                    m.value: sum(1 for p in self._proposals.values() if p.mode == m)
                    for m in ConsensusMode
                },
            }
