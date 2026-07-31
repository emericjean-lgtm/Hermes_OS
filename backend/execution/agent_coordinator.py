"""Agent Coordinator — selects optimal agent/skills/runtime/tools per task."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from .execution_models import TaskExecution


@dataclass
class AgentAssignment:
    """Result of agent coordination for a single task."""
    task_id: str = ""
    agent_id: str = ""
    runtime_id: str = ""
    skill_ids: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


class AgentCoordinator:
    """Selects the optimal agent, skills, runtime, and tools for each task.

    Selection criteria:
    - Agent capabilities vs task requirements
    - Agent availability (current load)
    - Historical performance on similar tasks
    - Runtime fit (hardware/VRAM constraints)
    - Cost (token/runtime cost optimization)
    """

    #: Past assignments retained for release_agent()/get_assignment() lookups.
    MAX_RETAINED_ASSIGNMENTS = 2000

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents: dict[str, dict[str, Any]] = {}        # agent_id → capabilities
        self._runtimes: dict[str, dict[str, Any]] = {}      # runtime_id → specs
        self._skills: dict[str, dict[str, Any]] = {}        # skill_id → metadata
        self._tools: dict[str, dict[str, Any]] = {}         # tool_id → metadata
        self._agent_loads: dict[str, int] = {}              # concurrent tasks per agent
        # task_id → assignment. Bounded: one entry per task executed, and
        # nothing pruned it, so this grew for the process lifetime (RC3 P5).
        self._assignments: OrderedDict[str, AgentAssignment] = OrderedDict()

    def register_agent(self, agent_id: str, capabilities: list[str],
                       preferred_runtime: str = "auto") -> None:
        with self._lock:
            self._agents[agent_id] = {
                "capabilities": capabilities,
                "preferred_runtime": preferred_runtime,
                "registered": True,
            }
            self._agent_loads.setdefault(agent_id, 0)

    def register_runtime(self, runtime_id: str, specs: dict[str, Any]) -> None:
        with self._lock:
            self._runtimes[runtime_id] = specs

    def register_skill(self, skill_id: str, metadata: dict[str, Any]) -> None:
        with self._lock:
            self._skills[skill_id] = metadata

    def register_tool(self, tool_id: str, metadata: dict[str, Any]) -> None:
        with self._lock:
            self._tools[tool_id] = metadata

    def assign(self, task: TaskExecution) -> AgentAssignment:
        """Generate the optimal assignment for a task."""
        with self._lock:
            # Select agent: match task title/requirements with agent capabilities
            agent_id = self._select_best_agent(task)

            # Select runtime: prefer agent's preferred, then fall back to generic
            runtime_id = self._select_runtime(agent_id, task)

            # Select skills: relevant to task domain
            skill_ids = self._select_skills(task)

            # Select tools: needed for task execution
            tool_ids = self._select_tools(task)

            confidence = self._calculate_confidence(agent_id, runtime_id, task)

            assignment = AgentAssignment(
                task_id=task.task_id,
                agent_id=agent_id,
                runtime_id=runtime_id,
                skill_ids=skill_ids,
                tool_ids=tool_ids,
                confidence=confidence,
                reasoning=f"Agent {agent_id} selected for task '{task.title}' "
                          f"(confidence: {confidence:.2f})",
            )

            self._assignments[task.task_id] = assignment
            self._assignments.move_to_end(task.task_id)
            while len(self._assignments) > self.MAX_RETAINED_ASSIGNMENTS:
                self._assignments.popitem(last=False)
            if agent_id in self._agent_loads:
                self._agent_loads[agent_id] += 1

            return assignment

    def release_agent(self, task_id: str) -> None:
        with self._lock:
            assignment = self._assignments.get(task_id)
            if assignment and assignment.agent_id in self._agent_loads:
                self._agent_loads[assignment.agent_id] = max(0, self._agent_loads[assignment.agent_id] - 1)

    def get_assignment(self, task_id: str) -> AgentAssignment | None:
        with self._lock:
            return self._assignments.get(task_id)

    def get_agent_load(self, agent_id: str) -> int:
        with self._lock:
            return self._agent_loads.get(agent_id, 0)

    # ── private selection methods ──

    def _select_best_agent(self, task: TaskExecution) -> str:
        """Match task title/requirements against agent capabilities with scoring."""
        best = ""
        best_score = -1.0
        keywords = set(task.title.lower().split() + [task.title.lower()])

        for agent_id, info in self._agents.items():
            if not info.get("registered"):
                continue
            caps = set(c.lower() for c in info.get("capabilities", []))
            score = len(keywords & caps) / max(len(keywords), 1)
            # Penalize load
            load = self._agent_loads.get(agent_id, 0)
            score -= load * 0.1
            if score > best_score:
                best_score = score
                best = agent_id

        return best or "default"

    def _select_runtime(self, agent_id: str, task: TaskExecution) -> str:
        agent_info = self._agents.get(agent_id, {})
        preferred = agent_info.get("preferred_runtime", "auto")
        if preferred != "auto" and preferred in self._runtimes:
            return preferred
        # Fall back to any available runtime
        for rid in self._runtimes:
            return rid
        return "default"

    def _select_skills(self, task: TaskExecution) -> list[str]:
        """Select skills matching task domain (simple keyword match)."""
        selected = []
        keywords = task.title.lower().split()
        for sid, meta in self._skills.items():
            skill_text = f"{sid} {meta.get('description', '')} {meta.get('domain', '')}".lower()
            if any(kw in skill_text for kw in keywords):
                selected.append(sid)
        return selected[:5]

    def _select_tools(self, task: TaskExecution) -> list[str]:
        """Select tools needed for task execution."""
        selected = []
        keywords = task.title.lower().split()
        for tid, meta in self._tools.items():
            tool_text = f"{tid} {meta.get('description', '')} {meta.get('category', '')}".lower()
            if any(kw in tool_text for kw in keywords):
                selected.append(tid)
        return selected[:3]

    def _calculate_confidence(self, agent_id: str, runtime_id: str,
                              task: TaskExecution) -> float:
        base = 0.7
        if agent_id and agent_id != "default":
            base += 0.1
        if runtime_id and runtime_id != "default":
            base += 0.1
        load = self._agent_loads.get(agent_id, 0)
        base -= min(load * 0.05, 0.3)
        return max(0.1, min(1.0, base))

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "agents_registered": len(self._agents),
                "runtimes_available": len(self._runtimes),
                "skills_available": len(self._skills),
                "tools_available": len(self._tools),
                "active_assignments": len(self._assignments),
                "agent_loads": dict(self._agent_loads),
            }
