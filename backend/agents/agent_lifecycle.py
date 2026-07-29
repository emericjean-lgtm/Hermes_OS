"""Agent Lifecycle Manager for the Agent Supervisor (HOS-043).

Manages the complete lifecycle of agents: creation → start → ready → busy → stop.
Thread-safe with state transition validation.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.agent_models import Agent, AgentStatus
from backend.agents.agent_registry import AgentRegistry


class AgentLifecycle:
    """Manages agent state transitions.

    Validates all state changes against a defined transition map.
    Thread-safe.
    """

    # Allowed transitions
    _TRANSITIONS: dict[AgentStatus, list[AgentStatus]] = {
        AgentStatus.CREATED: [AgentStatus.STARTING, AgentStatus.STOPPED],
        AgentStatus.STARTING: [AgentStatus.READY, AgentStatus.FAILED],
        AgentStatus.READY: [AgentStatus.BUSY, AgentStatus.PAUSED, AgentStatus.STOPPING, AgentStatus.FAILED],
        AgentStatus.BUSY: [AgentStatus.READY, AgentStatus.FAILED, AgentStatus.RECOVERING],
        AgentStatus.PAUSED: [AgentStatus.READY, AgentStatus.STOPPING],
        AgentStatus.FAILED: [AgentStatus.RECOVERING, AgentStatus.STOPPED],
        AgentStatus.RECOVERING: [AgentStatus.READY, AgentStatus.FAILED],
        AgentStatus.COMPLETED: [AgentStatus.STOPPED],
        AgentStatus.STOPPING: [AgentStatus.STOPPED],
        AgentStatus.STOPPED: [],  # terminal
    }

    def __init__(
        self,
        registry: AgentRegistry,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._registry = registry
        self._on_event = on_event
        self._history: dict[str, list[tuple[AgentStatus, str, datetime]]] = {}

    # ── Transitions ─────────────────────────────────────────

    def can_transition(self, agent: Agent, target: AgentStatus) -> bool:
        """Check if a transition is allowed."""
        return target in self._TRANSITIONS.get(agent.status, [])

    def transition(
        self,
        agent: Agent,
        target: AgentStatus,
        reason: str = "",
    ) -> bool:
        """Attempt a state transition. Returns True if successful."""
        if not self.can_transition(agent, target):
            return False

        old_status = agent.status
        agent.status = target
        agent.last_active_at = datetime.now(timezone.utc)

        # Update registry
        self._registry.update_status(agent.agent_id, target)

        # Record history
        with self._lock:
            self._history.setdefault(agent.agent_id, []).append(
                (old_status, reason, datetime.now(timezone.utc))
            )

        # Emit event
        event_map = {
            AgentStatus.STARTING: ("agent.started", "info"),
            AgentStatus.READY: ("agent.ready", "info"),
            AgentStatus.BUSY: ("agent.busy", "info"),
            AgentStatus.PAUSED: ("agent.paused", "info"),
            AgentStatus.FAILED: ("agent.failed", "error"),
            AgentStatus.COMPLETED: ("agent.completed", "info"),
            AgentStatus.STOPPED: ("agent.stopped", "info"),
        }
        if target in event_map and self._on_event:
            ev_type, severity = event_map[target]
            self._on_event(ev_type, {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "previous_status": old_status.value,
                "new_status": target.value,
                "reason": reason,
            }, severity=severity)

        return True

    # ── Lifecycle Methods ────────────────────────────────────

    def create_agent(
        self,
        name: str,
        capabilities: list,
        preferred_runtime: str = "",
        preferred_model: str = "",
        **kwargs,
    ) -> Agent:
        """Create and register a new agent."""
        agent = Agent(
            name=name,
            capabilities=list(capabilities),
            preferred_runtime=preferred_runtime,
            preferred_model=preferred_model,
            **kwargs,
        )
        self._registry.register(agent)

        if self._on_event:
            self._on_event("agent.created", {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "capabilities": [c.value for c in agent.capabilities],
            }, severity="info")

        return agent

    def start(self, agent: Agent) -> bool:
        """Start an agent: CREATED → STARTING → READY."""
        if not self.transition(agent, AgentStatus.STARTING, "Starting agent"):
            return False
        return self.transition(agent, AgentStatus.READY, "Agent ready")

    def stop(self, agent: Agent) -> bool:
        """Stop an agent: current → STOPPING → STOPPED."""
        if agent.status == AgentStatus.STOPPED:
            return True
        if not self.transition(agent, AgentStatus.STOPPING, "Stopping agent"):
            # Allow force stop
            agent.status = AgentStatus.STOPPED
            self._registry.update_status(agent.agent_id, AgentStatus.STOPPED)
            return True
        return self.transition(agent, AgentStatus.STOPPED, "Agent stopped")

    def pause(self, agent: Agent) -> bool:
        return self.transition(agent, AgentStatus.PAUSED, "Pausing agent")

    def resume(self, agent: Agent) -> bool:
        return self.transition(agent, AgentStatus.READY, "Resuming agent")

    def mark_busy(self, agent: Agent, task_id: str = "") -> bool:
        agent.current_task_id = task_id
        return self.transition(agent, AgentStatus.BUSY, f"Task assigned: {task_id}")

    def mark_ready(self, agent: Agent) -> bool:
        agent.current_task_id = ""
        return self.transition(agent, AgentStatus.READY, "Task completed")

    def mark_failed(self, agent: Agent, reason: str = "") -> bool:
        return self.transition(agent, AgentStatus.FAILED, reason)

    def recover(self, agent: Agent) -> bool:
        if not self.transition(agent, AgentStatus.RECOVERING, "Recovering"):
            return False
        return self.transition(agent, AgentStatus.READY, "Recovery successful")

    # ── History ──────────────────────────────────────────────

    def get_history(self, agent_id: str) -> list[dict]:
        with self._lock:
            entries = self._history.get(agent_id, [])
            return [
                {
                    "from": old.value,
                    "reason": reason,
                    "timestamp": ts.isoformat(),
                }
                for old, reason, ts in entries
            ]
