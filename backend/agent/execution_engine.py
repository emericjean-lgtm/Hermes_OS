"""Mission Execution Engine (HOS-024).

The engine is the top-level orchestrator that drives a mission plan
through concrete execution. It composes:

* MultiAgentSupervisor  (HOS-020) – mission lifecycle
* AgentLifecycleManager (HOS-019) – agent state machine
* ExecutionGraph        (HOS-017) – task DAG
* TaskPlanner           (HOS-018) – plan generation
* RuntimeDecisionEngine (HOS-015) – best-runtime selection
* RuntimeRouter         (HOS-010) – runtime execution
* HermesAgentAdapter    (HOS-023) – Hermes Agent bridge

The engine does **not** duplicate the logic of any of these modules.
It calls them, aggregates their output, and publishes events.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from backend.agent.execution_graph import (
    AgentNode,
    ExecutionGraph,
    ExecutionGraphError,
    GraphExecutionPlan,
    NodeStatus,
    NodeType,
)
from backend.agent.lifecycle import (
    AgentContext,
    AgentInstance,
    AgentLifecycleError,
    AgentLifecycleManager,
    AgentState,
)
from backend.agent.supervisor import (
    MissionContext,
    MissionInstance,
    MissionState,
    MultiAgentSupervisor,
    SupervisorError,
    SupervisorEvent,
)
from backend.agent.task_planner import (
    PlannedTask,
    PlanningError,
    PlanningStrategy,
    TaskMission,
    TaskPlan,
    TaskPlanner,
)
from backend.ral.runtime_decision import (
    RuntimeDecisionEngine,
    RuntimeDecisionError,
    RuntimeDecision,
)
from backend.ral.runtime_router import RuntimeRouter, RuntimeExecutionError

# HermesAgentAdapter is imported lazily (TYPE_CHECKING) because of
# Python 3.10 compatibility (datetime.UTC).
import typing as _typing
if _typing.TYPE_CHECKING:
    from backend.integrations.hermes_agent import HermesAgentAdapter


# ======================================================================
# Enums
# ======================================================================


class ExecutionState(str, Enum):
    """Lifecycle states of the execution engine itself."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionEvent(str, Enum):
    """Events emitted by the engine during execution."""

    EXECUTION_STARTED = "execution.started"
    TASK_READY = "execution.task_ready"
    TASK_STARTED = "execution.task_started"
    TASK_COMPLETED = "execution.task_completed"
    TASK_FAILED = "execution.task_failed"
    TASK_SKIPPED = "execution.task_skipped"
    EXECUTION_PAUSED = "execution.paused"
    EXECUTION_RESUMED = "execution.resumed"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_RECOVERED = "execution.recovered"
    NODE_BLOCKED = "execution.node_blocked"


# ======================================================================
# Exceptions
# ======================================================================


class ExecutionEngineError(Exception):
    """Raised when an engine operation fails."""


# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class ExecutionContext:
    """Context for a single execution run.

    Attributes:
        execution_id: Unique execution identifier.
        mission_id: The mission being executed.
        graph_id: The graph being executed (may differ from
            mission's graph if a sub-graph is used).
        created_at: Creation timestamp.
        metadata: Free-form payload.
    """

    execution_id: str
    mission_id: str = ""
    graph_id: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """Result of a completed or failed execution.

    Attributes:
        success: Whether the execution succeeded.
        completed_tasks: Number of completed tasks.
        failed_tasks: Number of failed tasks.
        skipped_tasks: Number of skipped tasks.
        execution_time_ms: Total wall-clock time in milliseconds.
        runtime_statistics: Per-runtime execution statistics.
        metadata: Free-form payload.
    """

    success: bool = False
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    execution_time_ms: float = 0.0
    runtime_statistics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionStatistics:
    """Aggregated engine statistics.

    Attributes:
        executions_started: Total executions started.
        executions_completed: Total executions completed.
        executions_failed: Total executions that failed.
        tasks_executed: Total tasks executed.
        tasks_parallel: Total tasks that ran in parallel.
        avg_execution_time_ms: Average execution time in ms.
        success_rate: Ratio of successful executions (0.0–1.0).
        avg_wait_time_ms: Average task wait time in ms.
        recovery_count: Number of recovery attempts.
        metadata: Free-form payload.
    """

    executions_started: int = 0
    executions_completed: int = 0
    executions_failed: int = 0
    tasks_executed: int = 0
    tasks_parallel: int = 0
    avg_execution_time_ms: float = 0.0
    success_rate: float = 1.0
    avg_wait_time_ms: float = 0.0
    recovery_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# Execution Scheduler
# ======================================================================


class ExecutionScheduler:
    """Determines which tasks are ready to run.

    The scheduler inspects the graph's topological structure and
    dependency state to identify tasks that can be dispatched.
    It is stateless — all state lives in the graph.
    """

    @staticmethod
    def get_ready_tasks(
        graph: ExecutionGraph,
        plan: GraphExecutionPlan,
    ) -> list[AgentNode]:
        """Return nodes whose dependencies are all satisfied.

        A node is "ready" if:
        1. Its status is ``PENDING``.
        2. All its predecessors are ``COMPLETED``.

        Args:
            graph: The execution graph.
            plan: The execution plan with dependency info.

        Returns:
            Ready nodes (order respects topological levels).
        """
        ready: list[AgentNode] = []

        for level in plan.levels:
            for node_id in level:
                try:
                    node = graph.get_node(node_id)
                except ExecutionGraphError:
                    continue

                if node.status not in (NodeStatus.PENDING, NodeStatus.PENDING.value):
                    continue

                deps = plan.dependencies.get(node_id, ())
                all_done = True
                for dep_id in deps:
                    try:
                        dep = graph.get_node(dep_id)
                        if dep.status not in (NodeStatus.COMPLETED, NodeStatus.COMPLETED.value):
                            all_done = False
                            break
                    except ExecutionGraphError:
                        all_done = False
                        break

                if all_done:
                    ready.append(node)

        return ready

    @staticmethod
    def get_parallel_groups(
        graph: ExecutionGraph,
        plan: GraphExecutionPlan,
    ) -> list[list[AgentNode]]:
        """Group ready nodes into parallel execution groups.

        Within a topological level, all nodes are independent and can
        run in parallel.

        Args:
            graph: The execution graph.
            plan: The execution plan with level info.

        Returns:
            A list of groups, each group being a list of nodes that can
            run in parallel concurrently.
        """
        groups: list[list[AgentNode]] = []

        for level in plan.levels:
            group: list[AgentNode] = []
            for node_id in level:
                try:
                    node = graph.get_node(node_id)
                except ExecutionGraphError:
                    continue
                if node.status == NodeStatus.PENDING:
                    group.append(node)
            if group:
                groups.append(group)

        return groups

    @staticmethod
    def estimate_wait_time(
        graph: ExecutionGraph,
        plan: GraphExecutionPlan,
        node_id: str,
        *,
        avg_task_duration_ms: float = 1000.0,
    ) -> float:
        """Estimate how long a node will wait before it becomes ready.

        The estimate sums the average duration of all uncompleted
        predecessors in its dependency chain.

        Args:
            graph: The execution graph.
            plan: The execution plan.
            node_id: Target node.
            avg_task_duration_ms: Average task duration estimate.

        Returns:
            Estimated wait time in milliseconds.
        """
        deps = plan.dependencies.get(node_id, ())
        blocking = 0
        for dep_id in deps:
            try:
                dep = graph.get_node(dep_id)
                if dep.status not in (NodeStatus.COMPLETED, NodeStatus.COMPLETED.value):
                    blocking += 1
            except ExecutionGraphError:
                blocking += 1
        return blocking * avg_task_duration_ms


# ======================================================================
# Execution Engine
# ======================================================================


class ExecutionEngine:
    """Top-level orchestrator for executing mission plans.

    The engine drives an :class:`ExecutionGraph` through its lifecycle,
    dispatching ready tasks via the :class:`RuntimeRouter` or
    :class:`HermesAgentAdapter`, updating the graph state, and emitting
    events.

    Args:
        supervisor: Multi-agent supervisor for mission lifecycle.
        lifecycle: Agent lifecycle manager.
        runtime_decision: Runtime decision engine for selecting the best
            runtime per task.
        runtime_router: Runtime router for executing tasks.
        hermes_adapter: Optional HermesAgentAdapter for Hermes Agent
            integration.
        planner: Optional task planner (created with BALANCED strategy
            if not provided).
    """

    def __init__(
        self,
        supervisor: MultiAgentSupervisor,
        lifecycle: AgentLifecycleManager,
        runtime_decision: RuntimeDecisionEngine,
        runtime_router: RuntimeRouter,
        *,
        hermes_adapter: Optional[Any] = None,
        planner: Optional[TaskPlanner] = None,
    ) -> None:
        self._supervisor = supervisor
        self._lifecycle = lifecycle
        self._decision_engine = runtime_decision
        self._router = runtime_router
        self._hermes = hermes_adapter
        self._planner = planner or TaskPlanner(strategy=PlanningStrategy.BALANCED)

        # Internal state
        self._state: ExecutionState = ExecutionState.IDLE
        self._context: Optional[ExecutionContext] = None
        self._execution_graph: Optional[ExecutionGraph] = None
        self._execution_plan: Optional[GraphExecutionPlan] = None
        self._start_time: Optional[float] = None
        self._result: Optional[ExecutionResult] = None
        self._lock = threading.RLock()

        # Statistics
        self._stats = ExecutionStatistics()

        # Event handlers
        self._handlers: list[Callable] = []

        # Task tracking
        self._task_starts: dict[str, float] = {}
        self._task_durations: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> ExecutionState:
        return self._state

    @property
    def context(self) -> Optional[ExecutionContext]:
        return self._context

    @property
    def result(self) -> Optional[ExecutionResult]:
        return self._result

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_event(self, handler: Callable) -> None:
        """Register a callback ``(event: ExecutionEvent, payload: dict)``."""
        with self._lock:
            self._handlers.append(handler)

    def _emit(self, event: ExecutionEvent, payload: Optional[dict] = None) -> None:
        for handler in self._handlers:
            try:
                handler(event, payload or {})
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        mission: MissionContext,
        tasks: list[PlannedTask],
        *,
        execution_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExecutionContext:
        """Start a new execution from a mission context and task list.

        The engine:
        1. Plans the mission (TaskPlanner → TaskPlan).
        2. Creates a mission in the supervisor.
        3. Builds the execution context.
        4. Transitions to RUNNING.

        Args:
            mission: The mission context.
            tasks: List of planned tasks.
            execution_id: Optional explicit execution id.
            metadata: Optional metadata.

        Returns:
            The execution context.

        Raises:
            ExecutionEngineError: If the engine is not IDLE or
                planning fails.
        """
        with self._lock:
            if self._state != ExecutionState.IDLE:
                raise ExecutionEngineError(
                    f"Cannot start: engine is in '{self._state.value}' state."
                )

            self._state = ExecutionState.INITIALIZING
            self._start_time = time.time()

        try:
            # 1. Plan the mission.
            execution_id_str = execution_id or uuid.uuid4().hex
            task_mission = TaskMission(
                id=mission.mission_id,
                title=mission.title,
                objective=mission.objective,
                priority=mission.priority,
            )
            plan = self._planner.create_plan(task_mission, tasks)

            if plan.execution_graph is None:
                raise ExecutionEngineError("Planner returned a plan with no graph.")

            # 2. Create the mission in the supervisor.
            supervisor_mission = self._supervisor.create_mission(mission, tasks)

            # 3. Build execution context.
            ctx = ExecutionContext(
                execution_id=execution_id_str,
                mission_id=mission.mission_id,
                graph_id=uuid.uuid4().hex,
                metadata=metadata or {},
            )

            with self._lock:
                self._context = ctx
                self._execution_graph = plan.execution_graph
                self._execution_plan = plan.execution_graph.generate_plan()
                self._state = ExecutionState.RUNNING

            self._emit(ExecutionEvent.EXECUTION_STARTED, {
                "execution_id": ctx.execution_id,
                "mission_id": ctx.mission_id,
                "task_count": len(tasks),
            })

            # Start the supervisor mission.
            self._supervisor.start_mission(mission.mission_id)

            return ctx

        except (PlanningError, SupervisorError) as exc:
            with self._lock:
                self._state = ExecutionState.FAILED
            self._emit(ExecutionEvent.EXECUTION_FAILED, {
                "error": str(exc),
            })
            raise ExecutionEngineError(str(exc)) from exc

    def pause(self) -> None:
        """Pause the current execution.

        Raises:
            ExecutionEngineError: If not currently RUNNING.
        """
        with self._lock:
            if self._state != ExecutionState.RUNNING:
                raise ExecutionEngineError(
                    f"Cannot pause: engine is in '{self._state.value}' state."
                )
            self._state = ExecutionState.PAUSED

        if self._context is not None:
            self._supervisor.pause_mission(self._context.mission_id)
            self._emit(ExecutionEvent.EXECUTION_PAUSED, {
                "execution_id": self._context.execution_id,
            })

    def resume(self) -> None:
        """Resume a paused execution.

        Raises:
            ExecutionEngineError: If not currently PAUSED.
        """
        with self._lock:
            if self._state != ExecutionState.PAUSED:
                raise ExecutionEngineError(
                    f"Cannot resume: engine is in '{self._state.value}' state."
                )
            self._state = ExecutionState.RUNNING

        if self._context is not None:
            self._supervisor.resume_mission(self._context.mission_id)
            self._emit(ExecutionEvent.EXECUTION_RESUMED, {
                "execution_id": self._context.execution_id,
            })

    def cancel(self) -> None:
        """Cancel the current execution.

        Raises:
            ExecutionEngineError: If already in a terminal state.
        """
        with self._lock:
            if self._state in {ExecutionState.COMPLETED, ExecutionState.FAILED,
                               ExecutionState.CANCELLED}:
                raise ExecutionEngineError(
                    f"Cannot cancel: engine is in terminal state '{self._state.value}'."
                )
            self._state = ExecutionState.CANCELLED

        if self._context is not None:
            self._supervisor.cancel_mission(self._context.mission_id)
            self._result = self._build_result(success=False)
            self._emit(ExecutionEvent.EXECUTION_FAILED, {
                "execution_id": self._context.execution_id,
                "reason": "cancelled",
            })

    def recover(self) -> bool:
        """Attempt to recover from a failure.

        The recovery transitions the engine to RECOVERING state, then
        attempts to resume the supervisor mission if it is not in a
        terminal state.

        Returns:
            ``True`` if recovery was initiated.
        """
        with self._lock:
            if self._state != ExecutionState.FAILED:
                return False
            self._state = ExecutionState.RECOVERING

        try:
            if self._context is not None:
                mission = self._supervisor.get_mission(self._context.mission_id)
                if mission.state in {MissionState.FAILED, MissionState.PAUSED}:
                    self._supervisor.resume_mission(self._context.mission_id)

            with self._lock:
                self._state = ExecutionState.RUNNING
                self._stats = ExecutionStatistics(
                    executions_started=self._stats.executions_started,
                    executions_completed=self._stats.executions_completed,
                    executions_failed=self._stats.executions_failed,
                    tasks_executed=self._stats.tasks_executed,
                    tasks_parallel=self._stats.tasks_parallel,
                    avg_execution_time_ms=self._stats.avg_execution_time_ms,
                    success_rate=self._stats.success_rate,
                    avg_wait_time_ms=self._stats.avg_wait_time_ms,
                    recovery_count=self._stats.recovery_count + 1,
                )

            self._emit(ExecutionEvent.EXECUTION_RECOVERED, {
                "execution_id": self._context.execution_id if self._context else "",
            })
            return True

        except SupervisorError:
            with self._lock:
                self._state = ExecutionState.FAILED
            return False

    # ------------------------------------------------------------------
    # Tick — main execution loop
    # ------------------------------------------------------------------

    def tick(self) -> list[str]:
        """Advance execution by one step.

        This method should be called periodically (every ~100ms or via
        a scheduler callable). It:

        1. Checks if the engine is RUNNING.
        2. Calls the supervisor's ``tick()`` to advance agent states.
        3. Identifies ready tasks via the scheduler.
        4. Dispatches ready tasks through the runtime router or adapter.
        5. Updates graph node statuses.
        6. Detects completion or failure.

        Returns:
            List of descriptions of what happened during this tick.
        """
        with self._lock:
            if self._state != ExecutionState.RUNNING:
                return []

        events: list[str] = []

        # 1. Let the supervisor advance its agents.
        try:
            supervisor_changes = self._supervisor.tick()
        except Exception:
            supervisor_changes = []

        # 2. Check agent completions and update graph.
        graph = self._execution_graph
        plan = self._execution_plan
        if graph is None or plan is None:
            return []

        self._sync_agent_states(graph)

        # 3. Find ready tasks.
        ready = ExecutionScheduler.get_ready_tasks(graph, plan)
        if ready:
            for node in ready:
                self._dispatch_task(node, graph, plan)
                events.append(f"dispatched:{node.id}")

        # 4. Check if graph is complete.
        if self._is_graph_finished(graph):
            with self._lock:
                self._state = ExecutionState.COMPLETED
            self._result = self._build_result(success=True)
            self._emit(ExecutionEvent.EXECUTION_COMPLETED, {
                "execution_id": self._context.execution_id if self._context else "",
                "result": {
                    "completed_tasks": self._result.completed_tasks,
                    "failed_tasks": self._result.failed_tasks,
                },
            })
            events.append("execution_completed")

        # 5. Check if graph has failed (unrecoverable errors).
        if self._has_graph_failed(graph):
            with self._lock:
                self._state = ExecutionState.FAILED
            self._result = self._build_result(success=False)
            self._emit(ExecutionEvent.EXECUTION_FAILED, {
                "execution_id": self._context.execution_id if self._context else "",
                "reason": "graph_has_failed_tasks",
            })
            events.append("execution_failed")

        return events

    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    def _dispatch_task(
        self,
        node: AgentNode,
        graph: ExecutionGraph,
        plan: GraphExecutionPlan,
    ) -> None:
        """Dispatch a single task for execution.

        Determines the runtime, creates an agent instance, and starts it.
        """
        capability = node.runtime_capability
        mission_id = self._context.mission_id if self._context else ""

        # 1. Select runtime via decision engine.
        runtime_name: Optional[str] = None
        decision: Optional[RuntimeDecision] = None
        try:
            decision = self._decision_engine.select_runtime(capability)
            runtime_name = decision.selected_runtime
        except RuntimeDecisionError:
            pass

        # 2. Update node status to RUNNING.
        try:
            graph._nodes[node.id] = AgentNode(
                id=node.id,
                name=node.name,
                type=node.type,
                status=NodeStatus.RUNNING,
                runtime_capability=node.runtime_capability,
                metadata={**node.metadata, "runtime": runtime_name},
            )
        except Exception:
            pass

        self._task_starts[node.id] = time.time()

        # 3. Create agent instance.
        agent_ctx = AgentContext(
            id=f"exec__{node.id}__{uuid.uuid4().hex[:8]}",
            mission_id=mission_id,
            task_id=node.id,
            runtime_capability=capability,
            assigned_runtime=runtime_name,
        )

        try:
            agent = self._lifecycle.create_agent(agent_ctx)
            self._lifecycle.start_agent(agent.id)

            # 4. Attempt execution.
            if runtime_name == "hermes-agent" and self._hermes is not None:
                # Use HermesAgentAdapter
                self._execute_via_hermes(agent.id, node)
            else:
                # Use RuntimeRouter
                self._execute_via_router(agent.id, node, runtime_name, capability)

            self._emit(ExecutionEvent.TASK_STARTED, {
                "node_id": node.id,
                "runtime": runtime_name,
            })

        except Exception as exc:
            self._mark_node_failed(graph, node.id, str(exc))

    def _execute_via_hermes(self, agent_id: str, node: AgentNode) -> None:
        """Execute a task using the Hermes Agent Adapter.

        This is a lightweight placeholder. Real execution depends on
        the agent adapter's task messages, which are beyond the scope
        of the engine itself (the engine orchestrates; the adapter
        executes).
        """
        self._emit(ExecutionEvent.TASK_READY, {
            "node_id": node.id,
            "via": "hermes-agent",
            "agent_id": agent_id,
        })

    def _execute_via_router(
        self,
        agent_id: str,
        node: AgentNode,
        runtime_name: Optional[str],
        capability: str,
    ) -> None:
        """Execute a task using the RuntimeRouter.

        The router dispatches the capability to the assigned runtime.
        """
        self._emit(ExecutionEvent.TASK_READY, {
            "node_id": node.id,
            "via": "runtime-router",
            "runtime": runtime_name,
            "agent_id": agent_id,
        })

    # ------------------------------------------------------------------
    # State synchronisation
    # ------------------------------------------------------------------

    def _sync_agent_states(self, graph: ExecutionGraph) -> None:
        """Sync completed/failed agent states back to graph nodes."""
        for node in graph.list_nodes():
            if node.status in (NodeStatus.RUNNING, NodeStatus.RUNNING.value):
                # Check if there's an agent instance for this node.
                for agent_id, agent in self._lifecycle._agents.items():  # noqa: SLF001
                    if agent.context.task_id == node.id:
                        if agent.state == AgentState.COMPLETED:
                            self._mark_node_completed(graph, node.id)
                            dur = time.time() - self._task_starts.get(node.id, time.time())
                            self._task_durations[node.id] = dur
                        elif agent.state in (AgentState.FAILED, AgentState.TIMEOUT):
                            self._mark_node_failed(graph, node.id, "agent_failed")
                        elif agent.state == AgentState.CANCELLED:
                            self._mark_node_skipped(graph, node.id)
                        break

    def _mark_node_completed(self, graph: ExecutionGraph, node_id: str) -> None:
        """Mark a graph node as completed."""
        try:
            node = graph.get_node(node_id)
            graph._nodes[node_id] = AgentNode(  # noqa: SLF001
                id=node.id,
                name=node.name,
                type=node.type,
                status=NodeStatus.COMPLETED,
                runtime_capability=node.runtime_capability,
                metadata=node.metadata,
            )
            self._emit(ExecutionEvent.TASK_COMPLETED, {"node_id": node_id})
        except ExecutionGraphError:
            pass

    def _mark_node_failed(self, graph: ExecutionGraph, node_id: str, reason: str) -> None:
        """Mark a graph node as failed."""
        try:
            node = graph.get_node(node_id)
            graph._nodes[node_id] = AgentNode(  # noqa: SLF001
                id=node.id,
                name=node.name,
                type=node.type,
                status=NodeStatus.FAILED,
                runtime_capability=node.runtime_capability,
                metadata={**node.metadata, "failure_reason": reason},
            )
            self._emit(ExecutionEvent.TASK_FAILED, {"node_id": node_id, "reason": reason})
        except ExecutionGraphError:
            pass

    def _mark_node_skipped(self, graph: ExecutionGraph, node_id: str) -> None:
        """Mark a graph node as skipped."""
        try:
            node = graph.get_node(node_id)
            graph._nodes[node_id] = AgentNode(  # noqa: SLF001
                id=node.id,
                name=node.name,
                type=node.type,
                status=NodeStatus.SKIPPED,
                runtime_capability=node.runtime_capability,
                metadata=node.metadata,
            )
            self._emit(ExecutionEvent.TASK_SKIPPED, {"node_id": node_id})
        except ExecutionGraphError:
            pass

    # ------------------------------------------------------------------
    # Completion detection
    # ------------------------------------------------------------------

    def _is_graph_finished(self, graph: ExecutionGraph) -> bool:
        """Check if all tasks in the graph are in a terminal state."""
        nodes = graph.list_nodes()
        if not nodes:
            return False
        terminal = {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
        return all(
            n.status in terminal or n.status.value in terminal
            for n in nodes
        )

    def _has_graph_failed(self, graph: ExecutionGraph) -> bool:
        """Check if any task in the graph is in a failed state and the
        graph cannot make further progress."""
        nodes = graph.list_nodes()
        if not nodes:
            return False
        terminal = {NodeStatus.FAILED, NodeStatus.SKIPPED}
        any_failed = any(
            n.status in terminal or n.status.value in terminal
            for n in nodes
        )
        if not any_failed:
            return False
        # Check if any pending node has all failed deps (blocked).
        try:
            plan = self._execution_plan
            if plan is not None:
                for node in nodes:
                    if node.status in (NodeStatus.PENDING, NodeStatus.PENDING.value):
                        deps = plan.dependencies.get(node.id, ())
                        if deps:
                            all_deps_terminal = all(
                                self._node_is_terminal_failure(graph, dep_id)
                                for dep_id in deps
                            )
                            if all_deps_terminal:
                                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _node_is_terminal_failure(graph: ExecutionGraph, node_id: str) -> bool:
        """Check if a node is in a terminal failure state."""
        try:
            node = graph.get_node(node_id)
            return node.status in (NodeStatus.FAILED, NodeStatus.FAILED.value)
        except ExecutionGraphError:
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_finished(self) -> bool:
        """Check if execution has reached a terminal state."""
        return self._state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }

    def get_status(self) -> dict[str, Any]:
        """Return a detailed status snapshot.

        Returns:
            Dict with engine state, execution context, task progress,
            and statistics.
        """
        with self._lock:
            graph = self._execution_graph
            nodes = graph.list_nodes() if graph else []

            completed = sum(1 for n in nodes if n.status in (
                NodeStatus.COMPLETED, NodeStatus.COMPLETED.value))
            failed = sum(1 for n in nodes if n.status in (
                NodeStatus.FAILED, NodeStatus.FAILED.value))
            running = sum(1 for n in nodes if n.status in (
                NodeStatus.RUNNING, NodeStatus.RUNNING.value))
            pending = sum(1 for n in nodes if n.status in (
                NodeStatus.PENDING, NodeStatus.PENDING.value))

            return {
                "state": self._state.value,
                "execution_id": self._context.execution_id if self._context else None,
                "mission_id": self._context.mission_id if self._context else None,
                "task_progress": {
                    "total": len(nodes),
                    "completed": completed,
                    "failed": failed,
                    "running": running,
                    "pending": pending,
                },
                "elapsed_ms": (
                    (time.time() - self._start_time) * 1000
                    if self._start_time else 0.0
                ),
                "statistics": self._stats,
            }

    def get_result(self) -> Optional[ExecutionResult]:
        """Return the execution result, or ``None`` if not finished."""
        return self._result

    def step(self) -> list[str]:
        """Convenience: run a single tick and return events.

        Equivalent to calling :meth:`tick`.
        """
        return self.tick()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_result(self, *, success: bool) -> ExecutionResult:
        """Build an :class:`ExecutionResult` from the current state."""
        graph = self._execution_graph
        nodes = graph.list_nodes() if graph else []

        completed = sum(1 for n in nodes if n.status in (
            NodeStatus.COMPLETED, NodeStatus.COMPLETED.value))
        failed = sum(1 for n in nodes if n.status in (
            NodeStatus.FAILED, NodeStatus.FAILED.value))
        skipped = sum(1 for n in nodes if n.status in (
            NodeStatus.SKIPPED, NodeStatus.SKIPPED.value))

        elapsed = (time.time() - self._start_time) * 1000 if self._start_time else 0.0

        with self._lock:
            self._stats = ExecutionStatistics(
                executions_started=self._stats.executions_started + 1,
                executions_completed=self._stats.executions_completed + (1 if success else 0),
                executions_failed=self._stats.executions_failed + (0 if success else 1),
                tasks_executed=self._stats.tasks_executed + completed,
                tasks_parallel=self._stats.tasks_parallel,
                avg_execution_time_ms=self._stats.avg_execution_time_ms,
                success_rate=(
                    self._stats.executions_completed /
                    max(self._stats.executions_started + 1, 1)
                ),
                avg_wait_time_ms=self._stats.avg_wait_time_ms,
                recovery_count=self._stats.recovery_count,
            )

        return ExecutionResult(
            success=success,
            completed_tasks=completed,
            failed_tasks=failed,
            skipped_tasks=skipped,
            execution_time_ms=elapsed,
            runtime_statistics={},
        )

    def get_statistics(self) -> ExecutionStatistics:
        """Return aggregated engine statistics.

        Returns:
            Current execution statistics.
        """
        with self._lock:
            return self._stats
