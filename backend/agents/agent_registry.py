"""Agent Registry for the Agent Supervisor (HOS-043).

Thread-safe registry of all agents with indexing by capability and status.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentMetrics,
    AgentStatus,
)


class AgentRegistry:
    """Thread-safe registry of all agents.

    Indexes agents by ID, capability, and status for efficient lookup.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, Agent] = {}
        self._by_capability: dict[AgentCapability, list[str]] = {c: [] for c in AgentCapability}
        self._by_status: dict[AgentStatus, list[str]] = {s: [] for s in AgentStatus}

    # ── CRUD ─────────────────────────────────────────────────

    def register(self, agent: Agent) -> None:
        """Register a new agent."""
        with self._lock:
            self._agents[agent.agent_id] = agent
            self._reindex(agent)

    def unregister(self, agent_id: str) -> bool:
        """Remove an agent from the registry."""
        with self._lock:
            agent = self._agents.pop(agent_id, None)
            if agent is None:
                return False
            self._deindex(agent)
            return True

    def get(self, agent_id: str) -> Optional[Agent]:
        with self._lock:
            return self._agents.get(agent_id)

    def list_all(self) -> list[Agent]:
        with self._lock:
            return list(self._agents.values())

    # ── Query by Capability ──────────────────────────────────

    def find_by_capability(self, capability: AgentCapability) -> list[Agent]:
        """Find all agents with a specific capability."""
        with self._lock:
            agent_ids = self._by_capability.get(capability, [])
            return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_by_capabilities(self, capabilities: list[AgentCapability]) -> list[Agent]:
        """Find agents that have ALL specified capabilities."""
        if not capabilities:
            return self.list_all()
        with self._lock:
            result_ids: set[str] | None = None
            for cap in capabilities:
                cap_ids = set(self._by_capability.get(cap, []))
                if result_ids is None:
                    result_ids = cap_ids
                else:
                    result_ids = result_ids & cap_ids
            if result_ids is None:
                return []
            return [self._agents[aid] for aid in result_ids if aid in self._agents]

    def find_by_any_capability(self, capabilities: list[AgentCapability]) -> list[Agent]:
        """Find agents that have ANY of the specified capabilities."""
        if not capabilities:
            return self.list_all()
        with self._lock:
            result_ids: set[str] = set()
            for cap in capabilities:
                result_ids.update(self._by_capability.get(cap, []))
            return [self._agents[aid] for aid in result_ids if aid in self._agents]

    # ── Query by Status ──────────────────────────────────────

    def find_by_status(self, status: AgentStatus) -> list[Agent]:
        with self._lock:
            agent_ids = self._by_status.get(status, [])
            return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def find_available(self) -> list[Agent]:
        """Find all agents ready to take tasks."""
        return self.find_by_status(AgentStatus.READY)

    # ── Update ───────────────────────────────────────────────

    def update_status(self, agent_id: str, new_status: AgentStatus) -> bool:
        """Update an agent's status, maintaining indexes."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return False
            old_status = agent.status
            agent.status = new_status
            agent.last_active_at = datetime.now(timezone.utc)
            # Update status index
            if agent_id in self._by_status.get(old_status, []):
                self._by_status[old_status].remove(agent_id)
            self._by_status[new_status].append(agent_id)
            return True

    def update_metrics(self, agent_id: str, duration_ms: float, success: bool) -> bool:
        """Update agent metrics after task completion."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                return False
            agent.total_tasks += 1
            agent.total_duration_ms += duration_ms
            if success:
                agent.successful_tasks += 1
            else:
                agent.failed_tasks += 1
            agent.last_active_at = datetime.now(timezone.utc)
            return True

    # ── Stats ────────────────────────────────────────────────

    def get_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        agent = self.get(agent_id)
        if agent is None:
            return None
        return AgentMetrics(
            agent_id=agent.agent_id,
            total_tasks=agent.total_tasks,
            successful_tasks=agent.successful_tasks,
            failed_tasks=agent.failed_tasks,
            avg_duration_ms=agent.total_duration_ms / max(agent.total_tasks, 1),
            success_rate=agent.success_rate,
            last_active=agent.last_active_at,
            current_load=agent.load,
        )

    def get_all_metrics(self) -> list[AgentMetrics]:
        metrics = []
        for agent in self.list_all():
            m = self.get_metrics(agent.agent_id)
            if m:
                metrics.append(m)
        return metrics

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._agents)
            ready = len(self._by_status.get(AgentStatus.READY, []))
            busy = len(self._by_status.get(AgentStatus.BUSY, []))
            failed = len(self._by_status.get(AgentStatus.FAILED, []))
            return {
                "total_agents": total,
                "ready": ready,
                "busy": busy,
                "failed": failed,
                "available": ready,
                "status_breakdown": {
                    s.value: len(self._by_status.get(s, [])) for s in AgentStatus
                },
            }

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._agents)

    # ── Helpers ──────────────────────────────────────────────

    def _reindex(self, agent: Agent) -> None:
        """Add agent to capability and status indexes."""
        for cap in agent.capabilities:
            self._by_capability[cap].append(agent.agent_id)
        self._by_status[agent.status].append(agent.agent_id)

    def _deindex(self, agent: Agent) -> None:
        """Remove agent from all indexes."""
        for cap in agent.capabilities:
            lst = self._by_capability.get(cap, [])
            if agent.agent_id in lst:
                lst.remove(agent.agent_id)
        lst = self._by_status.get(agent.status, [])
        if agent.agent_id in lst:
            lst.remove(agent.agent_id)
