"""Delegation Manager for the Multi-Agent Collaboration Engine (HOS-044).

Handles task delegation, expertise requests, context transfer, and result retrieval.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.collaboration.collaboration_models import (
    Delegation,
    DelegationStatus,
)


class DelegationManager:
    """Manages task delegations between agents.

    Supports: delegate task, request expertise, transfer context, retrieve result.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._delegations: dict[str, Delegation] = {}
        self._by_from: dict[str, list[str]] = {}
        self._by_to: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    def delegate(
        self,
        from_agent_id: str,
        to_agent_id: str,
        mission_id: str,
        node_id: str,
        title: str,
        description: str = "",
        reason: str = "",
        required_capabilities: Optional[list[str]] = None,
    ) -> Delegation:
        """Delegate a task to another agent."""
        d = Delegation(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            mission_id=mission_id,
            node_id=node_id,
            title=title,
            description=description,
            reason=reason,
            required_capabilities=required_capabilities or [],
        )
        return self._store(d)

    def request_expertise(
        self,
        from_agent_id: str,
        mission_id: str,
        title: str,
        description: str,
        required_capabilities: list[str],
    ) -> Delegation:
        """Request expertise — delegate to best matching agent (to be resolved later)."""
        d = Delegation(
            from_agent_id=from_agent_id,
            to_agent_id="",  # to be matched
            mission_id=mission_id,
            title=title,
            description=description,
            reason=f"Expertise needed: {', '.join(required_capabilities)}",
            required_capabilities=required_capabilities,
        )
        return self._store(d)

    def accept(self, delegation_id: str, agent_id: str) -> bool:
        """Accept a delegation."""
        return self._transition(delegation_id, agent_id, DelegationStatus.ACCEPTED)

    def reject(self, delegation_id: str, agent_id: str) -> bool:
        """Reject a delegation."""
        return self._transition(delegation_id, agent_id, DelegationStatus.REJECTED)

    def start(self, delegation_id: str, agent_id: str) -> bool:
        """Mark delegation as in progress."""
        return self._transition(delegation_id, agent_id, DelegationStatus.IN_PROGRESS)

    def complete(
        self, delegation_id: str, agent_id: str, summary: str = ""
    ) -> bool:
        """Mark delegation as completed."""
        with self._lock:
            d = self._delegations.get(delegation_id)
            if d is None or d.to_agent_id != agent_id:
                return False
            if d.status != DelegationStatus.IN_PROGRESS:
                return False
            d.status = DelegationStatus.COMPLETED
            d.completed_at = datetime.now(timezone.utc)
            d.result_summary = summary

        if self._on_event:
            self._on_event("task.delegated", {
                "delegation_id": delegation_id,
                "from": d.from_agent_id,
                "to": agent_id,
                "status": "completed",
            }, severity="info")
        return True

    def fail(self, delegation_id: str, agent_id: str) -> bool:
        with self._lock:
            d = self._delegations.get(delegation_id)
            if d is None or d.to_agent_id != agent_id:
                return False
            d.status = DelegationStatus.FAILED
            d.completed_at = datetime.now(timezone.utc)
        return True

    # ── Query ────────────────────────────────────────────────

    def get(self, delegation_id: str) -> Optional[Delegation]:
        return self._delegations.get(delegation_id)

    def get_incoming(self, agent_id: str) -> list[Delegation]:
        with self._lock:
            ids = self._by_to.get(agent_id, [])
            return [self._delegations[did] for did in ids if did in self._delegations]

    def get_outgoing(self, agent_id: str) -> list[Delegation]:
        with self._lock:
            ids = self._by_from.get(agent_id, [])
            return [self._delegations[did] for did in ids if did in self._delegations]

    def get_by_mission(self, mission_id: str) -> list[Delegation]:
        with self._lock:
            ids = self._by_mission.get(mission_id, [])
            return [self._delegations[did] for did in ids if did in self._delegations]

    def get_pending(self, agent_id: str) -> list[Delegation]:
        return [d for d in self.get_incoming(agent_id) if d.status == DelegationStatus.REQUESTED]

    def get_unmatched(self) -> list[Delegation]:
        """Get delegations that need expertise matching (no target agent)."""
        return [d for d in self._delegations.values() if d.to_agent_id == ""]

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._delegations),
                "by_status": {
                    s.value: sum(1 for d in self._delegations.values() if d.status == s)
                    for s in DelegationStatus
                },
                "pending": sum(1 for d in self._delegations.values() if d.status == DelegationStatus.REQUESTED),
            }

    # ── Helpers ──────────────────────────────────────────────

    def _store(self, d: Delegation) -> Delegation:
        with self._lock:
            self._delegations[d.delegation_id] = d
            self._by_from.setdefault(d.from_agent_id, []).append(d.delegation_id)
            if d.to_agent_id:
                self._by_to.setdefault(d.to_agent_id, []).append(d.delegation_id)
            if d.mission_id:
                self._by_mission.setdefault(d.mission_id, []).append(d.delegation_id)

        if self._on_event:
            self._on_event("task.delegated", {
                "delegation_id": d.delegation_id,
                "from": d.from_agent_id,
                "to": d.to_agent_id or "unmatched",
                "title": d.title,
            }, severity="info")
        return d

    def _transition(
        self, delegation_id: str, agent_id: str, new_status: DelegationStatus
    ) -> bool:
        with self._lock:
            d = self._delegations.get(delegation_id)
            if d is None:
                return False
            if d.to_agent_id and d.to_agent_id != agent_id:
                return False
            d.status = new_status
            if new_status in (DelegationStatus.ACCEPTED, DelegationStatus.COMPLETED):
                d.accepted_at = d.accepted_at or datetime.now(timezone.utc)
        return True
