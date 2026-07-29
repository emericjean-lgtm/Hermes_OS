"""Conflict Resolver for the Multi-Agent Collaboration Engine (HOS-044).

Detects and resolves conflicts between agents:
concurrent modifications, disagreements, resource conflicts, incompatible decisions.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.collaboration.collaboration_models import (
    Conflict,
    ConflictStatus,
    ConflictType,
)


class ConflictResolver:
    """Detects and resolves conflicts between agents.

    Supports automatic resolution strategies and escalation.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._conflicts: dict[str, Conflict] = {}
        self._by_mission: dict[str, list[str]] = {}
        self._by_agent: dict[str, list[str]] = {}

    def detect(
        self,
        conflict_type: ConflictType,
        agent_ids: list[str],
        mission_id: str,
        node_id: str,
        title: str,
        description: str,
        proposals: Optional[dict[str, str]] = None,
    ) -> Conflict:
        """Detect and register a new conflict."""
        c = Conflict(
            type=conflict_type,
            agent_ids=list(agent_ids),
            mission_id=mission_id,
            node_id=node_id,
            title=title,
            description=description,
            proposals=proposals or {},
        )
        return self._store(c)

    def propose_resolution(
        self, conflict_id: str, agent_id: str, resolution: str
    ) -> bool:
        """Propose a resolution for a conflict."""
        with self._lock:
            c = self._conflicts.get(conflict_id)
            if c is None:
                return False
            c.proposals[agent_id] = resolution
            c.status = ConflictStatus.PROPOSED
        return True

    def resolve(
        self, conflict_id: str, resolution: str, resolved_by: str = "auto"
    ) -> bool:
        """Resolve a conflict."""
        with self._lock:
            c = self._conflicts.get(conflict_id)
            if c is None:
                return False
            if c.status == ConflictStatus.RESOLVED:
                return False
            c.status = ConflictStatus.RESOLVED
            c.resolution = resolution
            c.resolved_by = resolved_by
            c.resolved_at = datetime.now(timezone.utc)

        if self._on_event:
            self._on_event("conflict.resolved", {
                "conflict_id": conflict_id,
                "type": c.type.value,
                "resolved_by": resolved_by,
            }, severity="info")
        return True

    def escalate(self, conflict_id: str) -> bool:
        """Escalate a conflict that can't be resolved automatically."""
        with self._lock:
            c = self._conflicts.get(conflict_id)
            if c is None:
                return False
            c.status = ConflictStatus.ESCALATED
        return True

    def auto_resolve(self, conflict_id: str) -> bool:
        """Attempt automatic resolution using simple strategies."""
        with self._lock:
            c = self._conflicts.get(conflict_id)
            if c is None:
                return False

            if c.type == ConflictType.DISAGREEMENT:
                # Pick the most common proposal, or first if tie
                if not c.proposals:
                    return False
                counts: dict[str, int] = {}
                for v in c.proposals.values():
                    counts[v] = counts.get(v, 0) + 1
                best = max(counts, key=counts.get)
                return self.resolve(conflict_id, best, "auto")

            elif c.type == ConflictType.RESOURCE_CONFLICT:
                # First-come-first-served basis
                first_agent = c.agent_ids[0] if c.agent_ids else ""
                return self.resolve(
                    conflict_id,
                    f"Resource allocated to {first_agent}",
                    "auto",
                )

            elif c.type == ConflictType.PRIORITY_CLASH:
                # Resolve by priority ordering
                return self.resolve(
                    conflict_id,
                    "Priority ordering applied",
                    "auto",
                )

            elif c.type == ConflictType.CONCURRENT_MODIFICATION:
                # Accept the first proposal
                first_value = next(iter(c.proposals.values()), "merged")
                return self.resolve(conflict_id, first_value, "auto")

            else:
                return self.resolve(
                    conflict_id,
                    "Conflict auto-resolved",
                    "auto",
                )

    # ── Query ────────────────────────────────────────────────

    def get(self, conflict_id: str) -> Optional[Conflict]:
        return self._conflicts.get(conflict_id)

    def get_by_mission(self, mission_id: str) -> list[Conflict]:
        with self._lock:
            ids = self._by_mission.get(mission_id, [])
            return [self._conflicts[cid] for cid in ids if cid in self._conflicts]

    def get_by_agent(self, agent_id: str) -> list[Conflict]:
        with self._lock:
            ids = self._by_agent.get(agent_id, [])
            return [self._conflicts[cid] for cid in ids if cid in self._conflicts]

    def get_active(self) -> list[Conflict]:
        with self._lock:
            return [c for c in self._conflicts.values()
                    if c.status != ConflictStatus.RESOLVED]

    def get_resolved(self) -> list[Conflict]:
        with self._lock:
            return [c for c in self._conflicts.values()
                    if c.status == ConflictStatus.RESOLVED]

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._conflicts),
                "active": len(self.get_active()),
                "resolved": len(self.get_resolved()),
                "by_type": {
                    t.value: sum(1 for c in self._conflicts.values() if c.type == t)
                    for t in ConflictType
                },
            }

    # ── Helpers ──────────────────────────────────────────────

    def _store(self, c: Conflict) -> Conflict:
        with self._lock:
            self._conflicts[c.conflict_id] = c
            if c.mission_id:
                self._by_mission.setdefault(c.mission_id, []).append(c.conflict_id)
            for aid in c.agent_ids:
                self._by_agent.setdefault(aid, []).append(c.conflict_id)

        if self._on_event:
            self._on_event("conflict.detected", {
                "conflict_id": c.conflict_id,
                "type": c.type.value,
                "agent_ids": c.agent_ids,
            }, severity="warning")
        return c
