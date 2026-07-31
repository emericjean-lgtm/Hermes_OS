"""Agent Lifecycle Manager (HOS-019).

Manages the lifecycle of Hermes OS agents — creation, scheduling,
execution, pausing, resuming, cancellation, completion and timeout —
independently of any concrete LLM provider or runtime backend.

The lifecycle manager implements a strict state machine (:class:`AgentState`)
and enforces valid transitions at runtime. Every state change emits a
:class:`LifecycleEvent` that can be consumed by observers.

No concrete agent (Coder, QA, etc.) is imported here.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentState(str, Enum):
    """Canonical lifecycle states of an agent instance.

    Valid transitions::

        CREATED → READY
        READY   → SCHEDULED
        SCHEDULED → RUNNING
        RUNNING → PAUSED | COMPLETED | FAILED | CANCELLED | TIMEOUT
        PAUSED  → RUNNING | CANCELLED | TIMEOUT
        Any terminal: COMPLETED, FAILED, CANCELLED, TIMEOUT
    """

    CREATED = "created"
    READY = "ready"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class LifecycleEvent(str, Enum):
    """Events emitted by the manager on state transitions."""

    CREATED = "lifecycle.created"
    STARTED = "lifecycle.started"
    PAUSED = "lifecycle.paused"
    RESUMED = "lifecycle.resumed"
    COMPLETED = "lifecycle.completed"
    FAILED = "lifecycle.failed"
    CANCELLED = "lifecycle.cancelled"
    TIMEOUT = "lifecycle.timeout"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentContext:
    """Contextual information attached to an agent instance.

    Attributes:
        id: Unique agent instance identifier.
        mission_id: Optional mission that spawned this agent.
        task_id: Optional task within a graph that this agent executes.
        runtime_capability: Required RAL capability (e.g. ``"chat"``).
        assigned_runtime: Name of the runtime assigned (optional).
        metadata: Free-form payload.
    """

    id: str
    mission_id: str = ""
    task_id: str = ""
    runtime_capability: str = "chat"
    assigned_runtime: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStatistics:
    """Execution statistics accumulated over an agent's lifetime.

    Attributes:
        execution_count: Number of times the agent was started.
        retries: Number of automatic retries performed.
        failures: Number of failures encountered.
        total_duration: Cumulative wall-clock duration in seconds.
        last_execution: Unix timestamp of the last execution start.
        metadata: Free-form metadata.
    """

    execution_count: int = 0
    retries: int = 0
    failures: int = 0
    total_duration: float = 0.0
    last_execution: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInstance:
    """Immutable snapshot of an agent at a point in time.

    Attributes:
        id: Unique instance identifier.
        state: Current lifecycle state.
        context: Agent context.
        created_at: Timestamp of creation.
        started_at: Timestamp of the latest start (or ``None``).
        finished_at: Timestamp of termination (or ``None``).
        statistics: Accumulated execution statistics.
        metadata: Free-form payload.
    """

    id: str
    state: AgentState
    context: AgentContext
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    statistics: AgentStatistics = field(default_factory=AgentStatistics)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentLifecycleError(Exception):
    """Raised when a lifecycle operation is invalid."""


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.CREATED: {AgentState.READY},
    AgentState.READY: {AgentState.SCHEDULED, AgentState.RUNNING},
    AgentState.SCHEDULED: {AgentState.RUNNING},
    AgentState.RUNNING: {AgentState.PAUSED, AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED, AgentState.TIMEOUT},
    AgentState.PAUSED: {AgentState.RUNNING, AgentState.CANCELLED, AgentState.TIMEOUT},
    AgentState.WAITING: {AgentState.RUNNING, AgentState.CANCELLED, AgentState.FAILED},
    AgentState.COMPLETED: set(),  # terminal
    AgentState.FAILED: set(),     # terminal
    AgentState.CANCELLED: set(),  # terminal
    AgentState.TIMEOUT: set(),    # terminal
}

# Map of target states → LifecycleEvent
_TRANSITION_EVENTS: dict[AgentState, LifecycleEvent] = {
    AgentState.READY: LifecycleEvent.CREATED,
    AgentState.RUNNING: LifecycleEvent.STARTED,
    AgentState.PAUSED: LifecycleEvent.PAUSED,
    AgentState.COMPLETED: LifecycleEvent.COMPLETED,
    AgentState.FAILED: LifecycleEvent.FAILED,
    AgentState.CANCELLED: LifecycleEvent.CANCELLED,
    AgentState.TIMEOUT: LifecycleEvent.TIMEOUT,
}

# ── resume: PAUSED → RUNNING emits RESUMED, not STARTED ──
_RESUME_TRANSITION: dict[AgentState, AgentState] = {
    AgentState.PAUSED: AgentState.RUNNING,
}


class AgentLifecycleManager:
    """Thread-safe manager of agent lifecycle state machines.

    The manager stores active agent instances in memory. Each instance
    transitions through the :class:`AgentState` machine, with strict
    validation of every transition.

    Args:
        timeout_s: Default timeout in seconds for agent execution.
            Agents that exceed this duration may be transitioned to
            ``TIMEOUT`` by :meth:`check_timeouts`.
    """

    def __init__(self, timeout_s: float = 300.0) -> None:
        self._timeout_s = timeout_s
        self._agents: dict[str, AgentInstance] = {}
        self._lock = threading.RLock()
        self._event_handlers: list[callable] = []

    def on_event(self, handler: callable) -> None:
        """Register a callback that receives ``(agent_id, from_state, to_state)``
        on every state transition.

        Args:
            handler: Callable accepting ``(agent_id: str, from_state: AgentState,
                to_state: AgentState)``.
        """
        with self._lock:
            self._event_handlers.append(handler)

    # ------------------------------------------------------------------
    # Agent lifecycle operations
    # ------------------------------------------------------------------

    def create_agent(
        self,
        context: AgentContext,
        *,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentInstance:
        """Create a new agent in ``CREATED`` state.

        Args:
            context: Agent context.
            metadata: Optional metadata.

        Returns:
            The newly created agent instance.

        Raises:
            AgentLifecycleError: If an agent with the same id already exists.
        """
        with self._lock:
            if context.id in self._agents:
                raise AgentLifecycleError(
                    f"Agent '{context.id}' already exists."
                )

            instance = AgentInstance(
                id=context.id,
                state=AgentState.CREATED,
                context=context,
                created_at=time.time(),
                metadata=metadata or {},
            )
            self._agents[context.id] = instance
            self._emit(context.id, AgentState.CREATED, AgentState.READY)
            # Immediately advance to READY after creation.
            return self._transition(context.id, AgentState.READY)

    def start_agent(self, agent_id: str) -> AgentInstance:
        """Transition an agent from ``READY`` or ``SCHEDULED`` → ``RUNNING``.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.

        Raises:
            AgentLifecycleError: If the agent does not exist or
                transition is invalid.
        """
        with self._lock:
            instance = self._get(agent_id)
            # Allow SCHEDULED → RUNNING directly.
            if instance.state == AgentState.SCHEDULED:
                return self._transition(agent_id, AgentState.RUNNING)
            return self._transition(agent_id, AgentState.RUNNING)

    def pause_agent(self, agent_id: str) -> AgentInstance:
        """Pause a running agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.

        Raises:
            AgentLifecycleError: If the agent is not currently running.
        """
        with self._lock:
            return self._transition(agent_id, AgentState.PAUSED)

    def resume_agent(self, agent_id: str) -> AgentInstance:
        """Resume a paused agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.
        """
        with self._lock:
            instance = self._get(agent_id)
            if instance.state != AgentState.PAUSED:
                raise AgentLifecycleError(
                    f"Cannot resume agent '{agent_id}' in state "
                    f"'{instance.state.value}'. Expected 'paused'."
                )
            self._emit(agent_id, instance.state, AgentState.RUNNING)
            now = time.time()
            updated = AgentInstance(
                id=instance.id,
                state=AgentState.RUNNING,
                context=instance.context,
                created_at=instance.created_at,
                started_at=instance.started_at or now,
                finished_at=None,
                statistics=instance.statistics,
                metadata=instance.metadata,
            )
            self._agents[agent_id] = updated
            return updated

    def cancel_agent(self, agent_id: str) -> AgentInstance:
        """Cancel an agent regardless of its current state.

        Non-terminal states transition to ``CANCELLED``.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.

        Raises:
            AgentLifecycleError: If the agent does not exist or is
                already in a terminal state.
        """
        with self._lock:
            return self._transition(agent_id, AgentState.CANCELLED)

    def complete_agent(self, agent_id: str) -> AgentInstance:
        """Mark an agent as successfully completed.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.
        """
        with self._lock:
            return self._transition(agent_id, AgentState.COMPLETED)

    def fail_agent(self, agent_id: str) -> AgentInstance:
        """Mark an agent as failed.

        Args:
            agent_id: Agent identifier.

        Returns:
            Updated agent instance.
        """
        with self._lock:
            return self._transition(agent_id, AgentState.FAILED)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> AgentInstance:
        """Return the current snapshot of an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            The current agent instance.

        Raises:
            AgentLifecycleError: If the agent does not exist.
        """
        with self._lock:
            return self._get(agent_id)

    def list_agents(
        self,
        *,
        state: Optional[AgentState] = None,
    ) -> list[AgentInstance]:
        """Return agents, optionally filtered by state.

        Args:
            state: Optional state filter.

        Returns:
            A list of agent instance snapshots.
        """
        with self._lock:
            agents = list(self._agents.values())
            if state is not None:
                agents = [a for a in agents if a.state == state]
            return agents

    def cleanup(self, max_age_s: float = 3600.0) -> int:
        """Remove agents that have been in a terminal state for too long.

        Args:
            max_age_s: Maximum age in seconds for terminal agents.

        Returns:
            Number of agents removed.
        """
        with self._lock:
            now = time.time()
            to_remove: list[str] = []
            for a_id, instance in self._agents.items():
                if instance.finished_at is not None and (now - instance.finished_at) > max_age_s:
                    if instance.state in {
                        AgentState.COMPLETED, AgentState.FAILED,
                        AgentState.CANCELLED, AgentState.TIMEOUT,
                    }:
                        to_remove.append(a_id)
            for a_id in to_remove:
                del self._agents[a_id]
            return len(to_remove)

    def check_timeouts(self) -> list[str]:
        """Transition running agents that exceed the timeout to ``TIMEOUT``.

        Returns:
            List of agent ids that were timed out.
        """
        with self._lock:
            now = time.time()
            timed_out: list[str] = []
            for a_id, instance in list(self._agents.items()):
                if instance.state == AgentState.RUNNING:
                    if instance.started_at is not None:
                        elapsed = now - instance.started_at
                        if elapsed > self._timeout_s:
                            try:
                                self._transition(a_id, AgentState.TIMEOUT)
                                timed_out.append(a_id)
                            except AgentLifecycleError:
                                pass
            return timed_out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, agent_id: str) -> AgentInstance:
        """Get agent or raise."""
        if agent_id not in self._agents:
            raise AgentLifecycleError(f"Agent '{agent_id}' not found.")
        return self._agents[agent_id]

    def _transition(self, agent_id: str, target: AgentState) -> AgentInstance:
        """Enforce state machine transition and update in place.

        Args:
            agent_id: Agent identifier.
            target: Target state.

        Returns:
            Updated agent instance.

        Raises:
            AgentLifecycleError: If the transition is not allowed.
        """
        instance = self._get(agent_id)
        current = instance.state

        # Allow CANCELLED from any non-terminal state.
        if target == AgentState.CANCELLED:
            if current in {
                AgentState.COMPLETED, AgentState.FAILED,
                AgentState.CANCELLED, AgentState.TIMEOUT,
            }:
                raise AgentLifecycleError(
                    f"Cannot cancel agent '{agent_id}': already in terminal "
                    f"state '{current.value}'."
                )
        elif target not in _ALLOWED_TRANSITIONS.get(current, set()):
            raise AgentLifecycleError(
                f"Invalid transition '{current.value}' → '{target.value}' "
                f"for agent '{agent_id}'."
            )

        now = time.time()
        started = instance.started_at
        finished = instance.finished_at
        stats = instance.statistics

        if target == AgentState.RUNNING:
            started = started or now
        elif target in {
            AgentState.COMPLETED, AgentState.FAILED,
            AgentState.CANCELLED, AgentState.TIMEOUT,
        }:
            finished = now
            duration = 0.0
            if started is not None:
                duration = now - started
            stats = AgentStatistics(
                execution_count=stats.execution_count + 1,
                retries=stats.retries,
                failures=stats.failures + (1 if target == AgentState.FAILED else 0),
                total_duration=stats.total_duration + duration,
                last_execution=started or now,
                metadata=stats.metadata,
            )

        updated = AgentInstance(
            id=instance.id,
            state=target,
            context=instance.context,
            created_at=instance.created_at,
            started_at=started,
            finished_at=finished,
            statistics=stats,
            metadata=instance.metadata,
        )
        self._agents[agent_id] = updated
        self._emit(agent_id, current, target)
        return updated

    def _emit(self, agent_id: str, from_state: AgentState, to_state: AgentState) -> None:
        """Notify registered event handlers."""
        for handler in self._event_handlers:
            try:
                handler(agent_id, from_state, to_state)
            except Exception:
                pass  # handlers must not crash the manager
