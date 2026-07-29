"""Audit Log for HOS-046.

Journals all governance decisions: who, what, when, why, result, duration.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.policy.policy_models import AuditAction, AuditEntry


class AuditLog:
    """Immutable audit trail of all governance decisions.

    Journals: who, what, when, why, result, duration.
    Thread-safe.
    """

    def __init__(
        self,
        max_entries: int = 10000,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._on_event = on_event
        self._entries: list[AuditEntry] = []
        self._by_agent: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    def log(
        self,
        action: AuditAction,
        agent_id: str = "",
        user_id: str = "",
        operation: str = "",
        mission_id: str = "",
        node_id: str = "",
        decision: str = "",
        reason: str = "",
        details: Optional[dict[str, Any]] = None,
        duration_ms: float = 0.0,
    ) -> AuditEntry:
        """Record an audit entry."""
        entry = AuditEntry(
            action=action,
            agent_id=agent_id,
            user_id=user_id,
            operation=operation,
            mission_id=mission_id,
            node_id=node_id,
            decision=decision,
            reason=reason,
            details=dict(details or {}),
            duration_ms=duration_ms,
        )
        with self._lock:
            self._entries.append(entry)
            self._by_agent.setdefault(agent_id, []).append(entry.audit_id)
            self._by_mission.setdefault(mission_id, []).append(entry.audit_id)
            # Auto-prune
            while len(self._entries) > self._max_entries:
                self._entries.pop(0)

        if self._on_event:
            self._on_event("audit.created", {
                "audit_id": entry.audit_id,
                "action": action.value,
                "operation": operation,
            }, severity="info")
        return entry

    def get(self, audit_id: str) -> Optional[AuditEntry]:
        with self._lock:
            for e in self._entries:
                if e.audit_id == audit_id:
                    return e
        return None

    def get_by_agent(self, agent_id: str) -> list[AuditEntry]:
        with self._lock:
            ids = set(self._by_agent.get(agent_id, []))
            return [e for e in self._entries if e.audit_id in ids]

    def get_by_mission(self, mission_id: str) -> list[AuditEntry]:
        with self._lock:
            ids = set(self._by_mission.get(mission_id, []))
            return [e for e in self._entries if e.audit_id in ids]

    def get_recent(self, limit: int = 50) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries[-limit:])

    def get_by_operation(self, operation: str, limit: int = 50) -> list[AuditEntry]:
        with self._lock:
            matches = [e for e in self._entries if e.operation == operation]
            return matches[-limit:]

    def query(
        self,
        agent_id: str = "",
        mission_id: str = "",
        operation: str = "",
        action: Optional[AuditAction] = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Flexible audit query."""
        with self._lock:
            results = list(self._entries)
            if agent_id:
                results = [e for e in results if e.agent_id == agent_id]
            if mission_id:
                results = [e for e in results if e.mission_id == mission_id]
            if operation:
                results = [e for e in results if e.operation == operation]
            if action:
                results = [e for e in results if e.action == action]
            return results[-limit:]

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_entries": len(self._entries),
                "max_entries": self._max_entries,
                "by_action": {
                    a.value: sum(1 for e in self._entries if e.action == a)
                    for a in AuditAction
                },
            }
