"""Task Dispatcher for the Agent Supervisor (HOS-043).

Receives MissionNodes, selects agents, creates contexts, dispatches tasks,
and tracks execution results.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.agents.agent_lifecycle import AgentLifecycle
from backend.agents.agent_models import (
    Agent,
    AgentStatus,
    ExecutionResult,
    TaskOutcome,
)
from backend.agents.agent_registry import AgentRegistry
from backend.agents.capability_matcher import CapabilityMatcher
from backend.agents.execution_context import ExecutionContextManager
from backend.mission.mission_models import Mission, MissionNode, NodeStatus


class TaskDispatcher:
    """Dispatches mission tasks to agents.

    Pipeline:
    1. Receive MissionNode
    2. Select best agent via CapabilityMatcher
    3. Create ExecutionContext
    4. Mark agent busy, update node status
    5. Execute (via callback)
    6. Record result, mark agent ready

    Thread-safe.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        lifecycle: AgentLifecycle,
        context_manager: ExecutionContextManager,
        matcher: CapabilityMatcher,
        on_event: Optional[Callable] = None,
        execute_callback: Optional[Callable[[Agent, MissionNode], bool]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._registry = registry
        self._lifecycle = lifecycle
        self._ctx_manager = context_manager
        self._matcher = matcher
        self._on_event = on_event
        self._execute_callback = execute_callback or (lambda a, n: True)
        self._results: dict[str, list[ExecutionResult]] = {}

    def dispatch(
        self,
        mission: Mission,
        node: MissionNode,
    ) -> Optional[ExecutionResult]:
        """Dispatch a single mission node to the best available agent.

        Returns the ExecutionResult, or None if dispatch failed.
        """
        # 1. Select agent
        agent = self._matcher.select_best(
            task_type=node.type,
            required_skills=node.required_skills,
            preferred_runtime=node.preferred_runtime,
            preferred_agent=node.preferred_agent,
        )

        if agent is None:
            if self._on_event:
                self._on_event("task.dispatch_failed", {
                    "node_id": node.node_id,
                    "title": node.title,
                    "reason": "No suitable agent available",
                }, severity="error")
            return None

        # 2. Create context
        ctx = self._ctx_manager.create_context(
            agent_id=agent.agent_id,
            mission_id=mission.mission_id,
            node_id=node.node_id,
            task_title=node.title,
            task_description=node.description,
            task_type=node.type,
            preferred_runtime=node.preferred_runtime,
            preferred_model=agent.preferred_model,
            benchmark_profile=node.benchmark_profile or agent.benchmark_profile,
            estimated_vram_gb=node.estimated_resources.get("vram_gb", 0.0),
            estimated_ram_gb=node.estimated_resources.get("ram_gb", 0.0),
            estimated_tokens=node.estimated_resources.get("tokens", 0),
            priority=node.priority.value if hasattr(node.priority, 'value') else str(node.priority),
        )

        # 3. Mark agent busy
        if not self._lifecycle.mark_busy(agent, task_id=node.node_id):
            self._ctx_manager.remove(ctx.context_id)
            return None

        # 4. Update node status
        node.status = NodeStatus.RUNNING
        node.started_at = datetime.now(timezone.utc)

        if self._on_event:
            self._on_event("task.assigned", {
                "mission_id": mission.mission_id,
                "node_id": node.node_id,
                "agent_id": agent.agent_id,
                "title": node.title,
            }, severity="info")

        # 5. Execute
        started = datetime.now(timezone.utc)
        success = self._execute_callback(agent, node)
        completed = datetime.now(timezone.utc)
        duration_ms = (completed - started).total_seconds() * 1000

        # 6. Record result
        result = ExecutionResult(
            context_id=ctx.context_id,
            agent_id=agent.agent_id,
            node_id=node.node_id,
            outcome=TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            summary=f"Executed by {agent.name}" if success else f"Failed on {agent.name}",
        )

        # 7. Update agent
        self._lifecycle.mark_ready(agent)
        self._registry.update_metrics(agent.agent_id, duration_ms, success)

        # Update node
        node.status = NodeStatus.COMPLETED if success else NodeStatus.FAILED
        node.completed_at = completed
        node.actual_duration_ms = duration_ms
        node.result_summary = result.summary

        # Store result
        with self._lock:
            self._results.setdefault(mission.mission_id, []).append(result)

        # Emit event
        if self._on_event:
            ev_type = "task.completed" if success else "task.failed"
            self._on_event(ev_type, {
                "mission_id": mission.mission_id,
                "node_id": node.node_id,
                "agent_id": agent.agent_id,
                "outcome": result.outcome.value,
                "duration_ms": duration_ms,
            }, severity="info" if success else "error")

        return result

    def reassign(
        self,
        mission: Mission,
        node: MissionNode,
        previous_agent_id: str,
    ) -> Optional[ExecutionResult]:
        """Reassign a failed task to a different agent."""
        if self._on_event:
            self._on_event("task.reassigned", {
                "mission_id": mission.mission_id,
                "node_id": node.node_id,
                "previous_agent_id": previous_agent_id,
            }, severity="warning")

        # Exclude the previous agent by temporarily changing its status
        prev_agent = self._registry.get(previous_agent_id)
        if prev_agent:
            prev_agent.status = AgentStatus.FAILED  # Make unavailable for matching

        result = self.dispatch(mission, node)

        # Restore previous agent status if still in registry
        if prev_agent and self._registry.get(previous_agent_id):
            prev_agent.status = AgentStatus.READY

        return result

    def get_results(self, mission_id: str) -> list[ExecutionResult]:
        with self._lock:
            return list(self._results.get(mission_id, []))

    def get_agent_results(self, agent_id: str) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        with self._lock:
            for rlist in self._results.values():
                for r in rlist:
                    if r.agent_id == agent_id:
                        results.append(r)
        return results
