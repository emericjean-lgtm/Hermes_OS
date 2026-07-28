"""Multi-Agent Supervisor (HOS-020).

Central orchestrator that coordinates mission planning, graph execution,
agent lifecycle and runtime selection.

The supervisor does **not** execute any concrete agent — it orchestrates
the preparation and coordinates the lifecycles. Concrete execution is
delegated to future HOS-021+ components.

Integrates:
- TaskPlanner (HOS-018)
- ExecutionGraph (HOS-017)
- AgentLifecycleManager (HOS-019)
- RuntimeDecisionEngine (HOS-015) — optional callback
- RuntimeRouter (HOS-010) — future

No concrete agent (Coder, QA, Freebuff, etc.) is imported here.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from backend.agent.execution_graph import ExecutionGraph, NodeStatus
from backend.agent.lifecycle import (
    AgentContext,
    AgentInstance,
    AgentLifecycleManager,
    AgentLifecycleError,
    AgentState,
)
from backend.agent.task_planner import (
    PlannedTask,
    PlanningError,
    PlanningStrategy,
    TaskMission,
    TaskPlan,
    TaskPlanner,
)


class MissionState(str, Enum):
    """Canonical lifecycle states for a mission."""

    CREATED = "created"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SupervisorEvent(str, Enum):
    """Events emitted by the supervisor on state changes."""

    MISSION_CREATED = "supervisor.mission_created"
    MISSION_STARTED = "supervisor.mission_started"
    MISSION_PAUSED = "supervisor.mission_paused"
    MISSION_RESUMED = "supervisor.mission_resumed"
    MISSION_COMPLETED = "supervisor.mission_completed"
    MISSION_FAILED = "supervisor.mission_failed"
    MISSION_CANCELLED = "supervisor.mission_cancelled"
    AGENT_CREATED = "supervisor.agent_created"
    AGENT_COMPLETED = "supervisor.agent_completed"
    AGENT_FAILED = "supervisor.agent_failed"
    TASK_READY = "supervisor.task_ready"
    GRAPH_COMPLETED = "supervisor.graph_completed"


class SupervisorError(Exception):
    """Raised when a supervisor operation is invalid."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MissionContext:
    """Context for a supervised mission.

    Attributes:
        mission_id: Unique mission identifier.
        title: Human-readable title.
        objective: Measurable objective.
        priority: Mission priority (1 = highest).
        metadata: Free-form payload.
    """

    mission_id: str
    title: str = ""
    objective: str = ""
    priority: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupervisorStatistics:
    """Aggregated statistics across all missions.

    Attributes:
        missions_started: Total missions started.
        missions_completed: Total missions completed.
        missions_failed: Total missions that failed.
        agents_created: Total agents created.
        agents_running: Current count of running agents.
        average_duration: Average mission duration in seconds.
        metadata: Free-form metadata.
    """

    missions_started: int = 0
    missions_completed: int = 0
    missions_failed: int = 0
    agents_created: int = 0
    agents_running: int = 0
    average_duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionInstance:
    """Snapshot of a mission at a point in time.

    Attributes:
        context: Mission context.
        state: Current mission state.
        task_plan: The generated task plan, if planning completed.
        agents: Agent ids launched for this mission, in order.
        statistics: Per-mission statistics.
        metadata: Free-form metadata.
    """

    context: MissionContext
    state: MissionState
    task_plan: Optional[TaskPlan] = None
    agents: tuple[str, ...] = ()
    statistics: SupervisorStatistics = field(default_factory=SupervisorStatistics)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Transition map for missions
# ---------------------------------------------------------------------------

_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.CREATED: {MissionState.PLANNING, MissionState.CANCELLED},
    MissionState.PLANNING: {MissionState.READY, MissionState.FAILED, MissionState.CANCELLED},
    MissionState.READY: {MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {MissionState.PAUSED, MissionState.COMPLETED, MissionState.FAILED, MissionState.CANCELLED},
    MissionState.PAUSED: {MissionState.RUNNING, MissionState.CANCELLED, MissionState.FAILED},
    MissionState.COMPLETED: set(),
    MissionState.FAILED: set(),
    MissionState.CANCELLED: set(),
}

_MISSION_EVENTS: dict[MissionState, SupervisorEvent] = {
    MissionState.PLANNING: SupervisorEvent.MISSION_CREATED,
    MissionState.READY: SupervisorEvent.MISSION_CREATED,
    MissionState.RUNNING: SupervisorEvent.MISSION_STARTED,
    MissionState.PAUSED: SupervisorEvent.MISSION_PAUSED,
    MissionState.COMPLETED: SupervisorEvent.MISSION_COMPLETED,
    MissionState.FAILED: SupervisorEvent.MISSION_FAILED,
    MissionState.CANCELLED: SupervisorEvent.MISSION_CANCELLED,
}


class MultiAgentSupervisor:
    """Central orchestrator for missions and agents.

    The supervisor owns a :class:`TaskPlanner` for plan generation and
    an :class:`AgentLifecycleManager` for agent lifecycle management.
    It drives mission progress through the :meth:`tick` method, which
    should be called periodically.

    Args:
        planner: The task planner to use.
        lifecycle: The agent lifecycle manager.
        runtime_selector_callback: Optional callable
            ``(capability: str) -> str | None`` that returns a runtime name
            for a given capability. If not provided, agent assignment
            is skipped (``assigned_runtime`` will be ``None``).
    """

    def __init__(
        self,
        planner: TaskPlanner,
        lifecycle: AgentLifecycleManager,
        *,
        runtime_selector_callback: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self._planner = planner
        self._lifecycle = lifecycle
        self._runtime_selector = runtime_selector_callback
        self._missions: dict[str, MissionInstance] = {}
        # Mission → agent ids for clean lookup
        self._mission_agents: dict[str, set[str]] = {}
        self._lock = threading.RLock()
        self._event_handlers: list[Callable] = []

    def on_event(self, handler: Callable) -> None:
        """Register a callback receiving ``(event: SupervisorEvent, mission_id: str)``."""
        with self._lock:
            self._event_handlers.append(handler)

    # ------------------------------------------------------------------
    # Mission lifecycle
    # ------------------------------------------------------------------

    def create_mission(
        self,
        context: MissionContext,
        tasks: list[PlannedTask],
    ) -> MissionInstance:
        """Create a new mission and immediately plan it.

        The planning step generates a task plan and execution graph.
        The mission transitions ``CREATED → PLANNING → READY``
        (or → ``FAILED`` if planning fails).

        Args:
            context: Mission context.
            tasks: List of tasks for the mission.

        Returns:
            The mission instance.

        Raises:
            SupervisorError: If a mission with the same id already exists.
        """
        with self._lock:
            if context.mission_id in self._missions:
                raise SupervisorError(
                    f"Mission '{context.mission_id}' already exists."
                )

            mission = MissionInstance(
                context=context,
                state=MissionState.CREATED,
            )
            self._missions[context.mission_id] = mission
            self._mission_agents[context.mission_id] = set()
            self._emit(SupervisorEvent.MISSION_CREATED, context.mission_id)

            # Transition to PLANNING
            mission = self._transition_mission(context.mission_id, MissionState.PLANNING)

            # Execute planning
            try:
                plan = self._planner.create_plan(
                    TaskMission(
                        id=context.mission_id,
                        title=context.title,
                        description=context.objective,
                        objective=context.objective,
                        priority=context.priority,
                    ),
                    tasks,
                )
            except PlanningError as exc:
                mission = self._transition_mission(
                    context.mission_id, MissionState.FAILED
                )
                return MissionInstance(
                    context=mission.context,
                    state=MissionState.FAILED,
                    metadata={**mission.metadata, "planning_error": str(exc)},
                )

            # Update stored mission with the plan before transitioning.
            self._missions[context.mission_id] = MissionInstance(
                context=mission.context,
                state=mission.state,
                task_plan=plan,
                agents=mission.agents,
                statistics=mission.statistics,
                metadata={"plan_generated_at": time.time()},
            )
            # Transition to READY (preserves task_plan).
            mission = self._transition_mission(context.mission_id, MissionState.READY)
            return mission

    def start_mission(self, mission_id: str) -> MissionInstance:
        """Start a mission that is in ``READY`` state.

        This transitions the mission to ``RUNNING``. Agents are created
        for root tasks during the first :meth:`tick` call.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.

        Raises:
            SupervisorError: If the mission does not exist or is not READY.
        """
        with self._lock:
            self._check_mission_exists(mission_id)
            return self._transition_mission(mission_id, MissionState.RUNNING)

    def pause_mission(self, mission_id: str) -> MissionInstance:
        """Pause a running mission.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        with self._lock:
            self._check_mission_exists(mission_id)
            mission = self._transition_mission(mission_id, MissionState.PAUSED)
            # Pause all running agents for this mission.
            for agent_id in self._mission_agents.get(mission_id, set()):
                try:
                    agent = self._lifecycle.get_agent(agent_id)
                    if agent.state == AgentState.RUNNING:
                        self._lifecycle.pause_agent(agent_id)
                except AgentLifecycleError:
                    pass
            return mission

    def resume_mission(self, mission_id: str) -> MissionInstance:
        """Resume a paused mission.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        with self._lock:
            self._check_mission_exists(mission_id)
            mission = self._transition_mission(mission_id, MissionState.RUNNING)
            # Resume all paused agents for this mission.
            for agent_id in self._mission_agents.get(mission_id, set()):
                try:
                    agent = self._lifecycle.get_agent(agent_id)
                    if agent.state == AgentState.PAUSED:
                        self._lifecycle.resume_agent(agent_id)
                except AgentLifecycleError:
                    pass
            return mission

    def cancel_mission(self, mission_id: str) -> MissionInstance:
        """Cancel a mission regardless of its current state.

        All non-terminal agents for this mission are cancelled.

        Args:
            mission_id: Mission identifier.

        Returns:
            Updated mission instance.
        """
        with self._lock:
            self._check_mission_exists(mission_id)
            mission = self._transition_mission(mission_id, MissionState.CANCELLED)
            # Cancel all non-terminal agents.
            for agent_id in self._mission_agents.get(mission_id, set()):
                try:
                    self._lifecycle.cancel_agent(agent_id)
                except AgentLifecycleError:
                    pass
            return mission

    # ------------------------------------------------------------------
    # Tick — drives execution forward
    # ------------------------------------------------------------------

    def tick(self) -> list[str]:
        """Advance all running missions by one step.

        For each running mission:
        1. Check if any running agents have completed/failed.
        2. Check if any ready tasks can become agent instances.
        3. Mark a mission as COMPLETED when the graph is done.
        4. Mark a mission as FAILED when an irrecoverable error occurs.

        Should be called periodically (e.g. every 100ms or via a scheduler).

        Returns:
            List of mission ids that changed state during this tick.
        """
        changed: list[str] = []
        with self._lock:
            for mid, mission in list(self._missions.items()):
                if mission.state == MissionState.RUNNING:
                    if self._tick_mission(mid):
                        changed.append(mid)
        return changed

    def _tick_mission(self, mission_id: str) -> bool:
        """Tick a single mission. Returns True if anything changed."""
        mission = self._get_mission(mission_id)
        plan = mission.task_plan
        if plan is None or plan.execution_graph is None:
            return False

        graph = plan.execution_graph
        task_lookup = {t.id: t for t in plan.tasks}

        # 1. Check completed agents and mark graph nodes.
        for agent_id in list(self._mission_agents.get(mission_id, set())):
            try:
                agent = self._lifecycle.get_agent(agent_id)
            except AgentLifecycleError:
                continue
            task_id = agent.context.task_id
            if not task_id:
                continue

            if agent.state == AgentState.COMPLETED:
                try:
                    node = graph.get_node(task_id)
                    graph._nodes[task_id] = type(node)(
                        id=node.id,
                        name=node.name,
                        type=node.type,
                        status=NodeStatus.COMPLETED,
                        runtime_capability=node.runtime_capability,
                        metadata=node.metadata,
                    )
                    self._emit(SupervisorEvent.AGENT_COMPLETED, mission_id)
                except Exception:
                    pass

            elif agent.state == AgentState.FAILED:
                try:
                    node = graph.get_node(task_id)
                    graph._nodes[task_id] = type(node)(
                        id=node.id,
                        name=node.name,
                        type=node.type,
                        status=NodeStatus.FAILED,
                        runtime_capability=node.runtime_capability,
                        metadata=node.metadata,
                    )
                    self._emit(SupervisorEvent.AGENT_FAILED, mission_id)
                except Exception:
                    pass

        # 2. Check graph completion.
        try:
            g_plan = graph.generate_plan()
        except Exception:
            g_plan = None

        if g_plan is not None:
            # All nodes are topologically sorted → check if all terminal.
            root_count = len(graph.get_roots())
            leaf_count = len(graph.get_leaves())

            if root_count == 0 and leaf_count == 0 and len(graph.list_nodes()) == 0:
                return False  # empty graph

            # If all leaves are COMPLETED, the graph is done.
            leaves = graph.get_leaves()
            all_done = all(
                n.status == NodeStatus.COMPLETED.value or n.status == NodeStatus.COMPLETED
                for n in leaves
            ) if leaves else False

            if all_done:
                self._transition_mission(mission_id, MissionState.COMPLETED)
                self._emit(SupervisorEvent.GRAPH_COMPLETED, mission_id)
                return True

        # 3. Find ready tasks and create agents.
        if g_plan is not None:
            for level in g_plan.levels:
                for node_id in level:
                    try:
                        node = graph.get_node(node_id)
                    except Exception:
                        continue
                    if node.status not in (NodeStatus.PENDING.value, NodeStatus.PENDING):
                        continue

                    # Check dependencies: all predecessors must be COMPLETED.
                    deps = g_plan.dependencies.get(node_id, ())
                    if deps:
                        all_deps_completed = True
                        for dep_id in deps:
                            try:
                                dep_node = graph.get_node(dep_id)
                                if dep_node.status not in (
                                    NodeStatus.COMPLETED.value, NodeStatus.COMPLETED,
                                ):
                                    all_deps_completed = False
                                    break
                            except Exception:
                                all_deps_completed = False
                                break
                        if not all_deps_completed:
                            continue

                    # This task is now ready — create an agent for it.
                    task = task_lookup.get(node_id)
                    if task is None:
                        continue

                    # Select runtime if callback provided.
                    assigned = None
                    if self._runtime_selector is not None:
                        assigned = self._runtime_selector(task.runtime_capability)

                    agent_ctx = AgentContext(
                        id=f"{mission_id}__{node_id}__{uuid.uuid4().hex[:8]}",
                        mission_id=mission_id,
                        task_id=node_id,
                        runtime_capability=task.runtime_capability,
                        assigned_runtime=assigned,
                    )

                    try:
                        agent = self._lifecycle.create_agent(agent_ctx)
                        self._mission_agents[mission_id].add(agent.id)
                        self._lifecycle.start_agent(agent.id)

                        # Update graph node status to RUNNING.
                        graph._nodes[node_id] = type(node)(
                            id=node.id,
                            name=node.name,
                            type=node.type,
                            status=NodeStatus.RUNNING,
                            runtime_capability=node.runtime_capability,
                            metadata=node.metadata,
                        )
                        self._emit(SupervisorEvent.AGENT_CREATED, mission_id)
                        self._emit(SupervisorEvent.TASK_READY, mission_id)
                    except Exception:
                        pass

        return True

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_mission(self, mission_id: str) -> MissionInstance:
        """Return the current snapshot of a mission.

        Args:
            mission_id: Mission identifier.

        Returns:
            Mission instance.
        """
        with self._lock:
            return self._get_mission(mission_id)

    def list_missions(
        self,
        *,
        state: Optional[MissionState] = None,
    ) -> list[MissionInstance]:
        """Return missions, optionally filtered by state.

        Args:
            state: Optional state filter.

        Returns:
            List of mission instances.
        """
        with self._lock:
            missions = list(self._missions.values())
            if state is not None:
                missions = [m for m in missions if m.state == state]
            return missions

    def get_statistics(self) -> SupervisorStatistics:
        """Return global supervisor statistics.

        Returns:
            Aggregated statistics.
        """
        with self._lock:
            total = 0.0
            count = 0
            started = 0
            completed = 0
            failed = 0
            agents_total = 0
            agents_running = 0

            for mid, mission in self._missions.items():
                if mission.state in {MissionState.COMPLETED, MissionState.RUNNING, MissionState.FAILED}:
                    started += 1
                if mission.state == MissionState.COMPLETED:
                    completed += 1
                if mission.state == MissionState.FAILED:
                    failed += 1
                agents_total += len(self._mission_agents.get(mid, set()))

            # Count running agents across all missions.
            for agent_list in self._mission_agents.values():
                for agent_id in agent_list:
                    try:
                        agent = self._lifecycle.get_agent(agent_id)
                        if agent.state == AgentState.RUNNING:
                            agents_running += 1
                    except AgentLifecycleError:
                        pass

            avg_duration = total / count if count else 0.0

            return SupervisorStatistics(
                missions_started=started,
                missions_completed=completed,
                missions_failed=failed,
                agents_created=agents_total,
                agents_running=agents_running,
                average_duration=avg_duration,
            )

    def cleanup(self, max_age_s: float = 3600.0) -> int:
        """Remove missions and agents that are in a terminal state.

        Args:
            max_age_s: Maximum age in seconds.

        Returns:
            Number of missions removed.
        """
        with self._lock:
            now = time.time()
            to_remove: list[str] = []
            for mid, mission in self._missions.items():
                if mission.state in {
                    MissionState.COMPLETED, MissionState.FAILED, MissionState.CANCELLED,
                }:
                    # Use metadata timestamp as proxy.
                    age = now - mission.metadata.get("plan_generated_at", now)
                    if age > max_age_s:
                        to_remove.append(mid)

            for mid in to_remove:
                # Clean up lifecycle agents.
                for agent_id in self._mission_agents.get(mid, set()):
                    try:
                        self._lifecycle.cancel_agent(agent_id)
                    except AgentLifecycleError:
                        pass
                del self._missions[mid]
                del self._mission_agents[mid]

            return len(to_remove)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_mission_exists(self, mission_id: str) -> None:
        """Raise SupervisorError if mission not found."""
        if mission_id not in self._missions:
            raise SupervisorError(f"Mission '{mission_id}' not found.")

    def _get_mission(self, mission_id: str) -> MissionInstance:
        self._check_mission_exists(mission_id)
        return self._missions[mission_id]

    def _transition_mission(
        self, mission_id: str, target: MissionState,
    ) -> MissionInstance:
        """Apply a state transition to a mission."""
        mission = self._get_mission(mission_id)
        current = mission.state

        if target not in _MISSION_TRANSITIONS.get(current, set()):
            raise SupervisorError(
                f"Invalid mission transition '{current.value}' → "
                f"'{target.value}' for mission '{mission_id}'."
            )

        now = time.time()
        updated = MissionInstance(
            context=mission.context,
            state=target,
            task_plan=mission.task_plan,
            agents=mission.agents,
            statistics=SupervisorStatistics(
                missions_started=mission.statistics.missions_started,
                missions_completed=mission.statistics.missions_completed,
                missions_failed=mission.statistics.missions_failed,
                agents_created=mission.statistics.agents_created,
            ),
            metadata={**mission.metadata, f"{target.value}_at": now},
        )
        self._missions[mission_id] = updated

        event = _MISSION_EVENTS.get(target)
        if event is not None:
            self._emit(event, mission_id)

        return updated

    def _emit(self, event: SupervisorEvent, mission_id: str) -> None:
        """Notify registered event handlers."""
        for handler in self._event_handlers:
            try:
                handler(event, mission_id)
            except Exception:
                pass
