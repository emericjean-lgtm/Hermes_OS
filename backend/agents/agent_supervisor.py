"""Agent Supervisor — central orchestrator for HOS-043.

Supervises all agents, dispatches mission tasks, monitors execution,
reassigns failed tasks, collects metrics, and publishes events.

Integrates with:
- Mission Graph (HOS-041): receives Mission/MissionNode
- Runtime Orchestrator (HOS-038): runtime selection callback
- Event Bus (HOS-034): publishes agent lifecycle events
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.agents.agent_lifecycle import AgentLifecycle
from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentMetrics,
    AgentStatus,
    ExecutionResult,
    TaskOutcome,
)
from backend.agents.agent_registry import AgentRegistry
from backend.agents.capability_matcher import CapabilityMatcher
from backend.agents.execution_context import ExecutionContextManager
from backend.agents.task_dispatcher import TaskDispatcher
from backend.mission.mission_models import Mission, MissionNode, NodeStatus


class AgentSupervisor:
    """Central supervisor for all agents.

    Coordinates agent lifecycle, task dispatch, execution tracking,
    and metrics collection. Thread-safe.

    HOS-070 audit finding: this class's own ``dispatch_node()``/
    ``execute_mission_step()``/``execute_full_mission()`` (and the
    ``TaskDispatcher``/``CapabilityMatcher`` selection they drive) are real
    but are not the path a real Mission or Autonomous goal actually takes —
    confirmed by a repo-wide search, nothing outside this file's own
    methods and its tests ever calls any of the three. The real execution
    path is ``backend/execution/mission_executor.py``'s ``MissionExecutor``,
    reached through ``GraphExecutor``/``node_execution.py``; since HOS-070
    it also syncs this class's own ``registry`` (status, load, metrics) and
    ``CapabilityMatcher`` (real agent selection) so this supervisor's data
    is accurate for the Cockpit even though its own dispatch methods are
    not what ran the task. What remains genuinely unused here: multi-node
    orchestration through this class's own DAG walk
    (``execute_mission_step``/``execute_full_mission``) and reassignment on
    failure (``reassign_node``) — GraphExecutor has its own, separate DAG
    walker and retry logic for those.
    """

    def __init__(
        self,
        on_event: Optional[Callable] = None,
        execute_callback: Optional[Callable[[Agent, MissionNode], bool]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._on_event = on_event
        self._execute_callback = execute_callback

        # Subsystems
        self._registry = AgentRegistry()
        self._lifecycle = AgentLifecycle(registry=self._registry, on_event=on_event)
        self._ctx_manager = ExecutionContextManager()
        self._matcher = CapabilityMatcher(registry=self._registry)
        self._dispatcher = TaskDispatcher(
            registry=self._registry,
            lifecycle=self._lifecycle,
            context_manager=self._ctx_manager,
            matcher=self._matcher,
            on_event=on_event,
            execute_callback=execute_callback,
        )

        # Tracking
        self._mission_assignments: dict[str, dict[str, str]] = {}  # mission_id → {node_id → agent_id}

    # ── Agent Management ─────────────────────────────────────

    def create_agent(
        self,
        name: str,
        capabilities: list[AgentCapability],
        preferred_runtime: str = "",
        preferred_model: str = "",
        description: str = "",
        **kwargs,
    ) -> Agent:
        """Create and register a new agent."""
        agent = self._lifecycle.create_agent(
            name=name,
            capabilities=capabilities,
            preferred_runtime=preferred_runtime,
            preferred_model=preferred_model,
            description=description,
            **kwargs,
        )
        self._lifecycle.start(agent)
        return agent

    def stop_agent(self, agent_id: str) -> bool:
        agent = self._registry.get(agent_id)
        if agent is None:
            return False
        return self._lifecycle.stop(agent)

    def pause_agent(self, agent_id: str) -> bool:
        agent = self._registry.get(agent_id)
        if agent is None:
            return False
        return self._lifecycle.pause(agent)

    def resume_agent(self, agent_id: str) -> bool:
        agent = self._registry.get(agent_id)
        if agent is None:
            return False
        return self._lifecycle.resume(agent)

    def recover_agent(self, agent_id: str) -> bool:
        agent = self._registry.get(agent_id)
        if agent is None:
            return False
        return self._lifecycle.recover(agent)

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._registry.get(agent_id)

    def list_agents(self, status: Optional[AgentStatus] = None) -> list[Agent]:
        if status:
            return self._registry.find_by_status(status)
        return self._registry.list_all()

    # ── Task Dispatch ────────────────────────────────────────

    def dispatch_node(self, mission: Mission, node: MissionNode) -> Optional[ExecutionResult]:
        """Dispatch a single mission node to an agent."""
        with self._lock:
            self._mission_assignments.setdefault(mission.mission_id, {})
            self._mission_assignments[mission.mission_id][node.node_id] = ""

        result = self._dispatcher.dispatch(mission, node)

        if result:
            with self._lock:
                self._mission_assignments[mission.mission_id][node.node_id] = result.agent_id

        return result

    def execute_mission_step(self, mission: Mission) -> dict[str, Any]:
        """Execute all ready nodes in a mission via available agents.

        Returns a summary of what was executed.
        """
        # Find ready nodes
        ready_nodes = [
            n for n in mission.nodes
            if n.status == NodeStatus.PENDING
            and self._dependencies_met(mission, n)
        ]

        results = {}
        for node in ready_nodes:
            result = self.dispatch_node(mission, node)
            if result:
                results[node.node_id] = {
                    "agent_id": result.agent_id,
                    "outcome": result.outcome.value,
                    "duration_ms": result.duration_ms,
                }
            else:
                results[node.node_id] = {
                    "error": "No agent available",
                }

        return {
            "mission_id": mission.mission_id,
            "nodes_dispatched": len(ready_nodes),
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def execute_full_mission(self, mission: Mission) -> dict[str, Any]:
        """Execute all nodes in a mission sequentially.

        This is a blocking call that processes the entire DAG.
        """
        total_nodes = len(mission.nodes)
        executed = 0
        failed = 0

        # Process in DAG order (max iterations = total nodes to prevent infinite loop)
        max_iterations = len(mission.nodes)
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            ready_nodes = [
                n for n in mission.nodes
                if n.status == NodeStatus.PENDING
                and self._dependencies_met(mission, n)
            ]
            if not ready_nodes:
                break

            for node in ready_nodes:
                result = self.dispatch_node(mission, node)
                executed += 1
                if result and result.outcome == TaskOutcome.FAILURE:
                    failed += 1

                # Optionally reassign on failure
                if result and result.outcome == TaskOutcome.FAILURE:
                    if self._dispatcher.reassign(mission, node, result.agent_id):
                        failed -= 1  # succeeded on reassignment

        return {
            "mission_id": mission.mission_id,
            "total_nodes": total_nodes,
            "executed": executed,
            "failed": failed,
            "progress_pct": round((executed - failed) / max(total_nodes, 1) * 100, 1),
        }

    # ── Reassignment ─────────────────────────────────────────

    def reassign_node(self, mission: Mission, node: MissionNode) -> Optional[ExecutionResult]:
        """Reassign a failed node to a different agent."""
        current_agent_id = ""
        with self._lock:
            current_agent_id = self._mission_assignments.get(
                mission.mission_id, {}
            ).get(node.node_id, "")

        return self._dispatcher.reassign(mission, node, current_agent_id)

    # ── Metrics & Stats ──────────────────────────────────────

    def get_agent_metrics(self, agent_id: str) -> Optional[AgentMetrics]:
        return self._registry.get_metrics(agent_id)

    def get_all_metrics(self) -> list[AgentMetrics]:
        return self._registry.get_all_metrics()

    def get_stats(self) -> dict:
        stats = self._registry.get_stats()
        stats["active_contexts"] = self._ctx_manager.count_active()
        return stats

    def get_agent_history(self, agent_id: str) -> list[dict]:
        return self._lifecycle.get_history(agent_id)

    def get_mission_results(self, mission_id: str) -> list[ExecutionResult]:
        return self._dispatcher.get_results(mission_id)

    def get_agent_tasks(self, agent_id: str) -> list[dict]:
        results = self._dispatcher.get_agent_results(agent_id)
        return [
            {
                "node_id": r.node_id,
                "outcome": r.outcome.value,
                "duration_ms": r.duration_ms,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in results
        ]

    # ── Helpers ──────────────────────────────────────────────

    def _dependencies_met(self, mission: Mission, node: MissionNode) -> bool:
        """Check if all dependencies of a node are completed."""
        if not node.depends_on:
            return True
        for dep_id in node.depends_on:
            dep_node = next((n for n in mission.nodes if n.node_id == dep_id), None)
            if dep_node is None or dep_node.status != NodeStatus.COMPLETED:
                return False
        return True

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    @property
    def lifecycle(self) -> AgentLifecycle:
        return self._lifecycle
