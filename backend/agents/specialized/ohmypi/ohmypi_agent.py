"""Oh My Pi Agent (HOS-055B).

Specialized agent for LSP editing, DAP debugging, AST manipulation,
code execution, and LLM routing via Oh My Pi.

Integrates with AgentSupervisor, Workspace, EventBus, and Memory.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.agents.agent_models import (
    Agent, AgentCapability, AgentMetrics, AgentProfile,
    AgentStatus, ExecutionResult, TaskOutcome,
)
from .ohmypi_capabilities import (
    OhMyPiTaskType, TASK_TO_CAPABILITY, TASK_TO_MCP_ACTION,
)
from .ohmypi_profile import OhMyPiProfile

OHMYPI_EVENTS = {
    "agent_ready": "ohmypi.agent.ready",
    "edit_started": "ohmypi.edit.started",
    "edit_completed": "ohmypi.edit.completed",
    "debug_started": "ohmypi.debug.started",
    "execution_completed": "ohmypi.execution.completed",
    "error": "ohmypi.error",
}


@dataclass
class OhMyPiTaskRecord:
    task_id: str = ""; task_type: str = ""; language: str = ""
    result: str = ""; duration_ms: float = 0.0; errors: list[str] = field(default_factory=list)
    mcp_action: str = ""; agent_id: str = ""; mission_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class OhMyPiAgent:
    def __init__(self, agent_id: str = "", on_event: Optional[Callable] = None,
                 mcp_adapter: Any = None, memory_manager: Any = None,
                 workspace_manager: Any = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._mcp_adapter = mcp_adapter
        self._memory_manager = memory_manager
        self._workspace_manager = workspace_manager
        self._profile = OhMyPiProfile()
        if not agent_id:
            import uuid; agent_id = f"ohmypi_{uuid.uuid4().hex[:8]}"
        self._agent_id = agent_id
        self._status = AgentStatus.CREATED
        self._current_task_id = ""; self._current_mission_id = ""
        self._total_tasks = 0; self._successful_tasks = 0; self._failed_tasks = 0
        self._total_duration_ms = 0.0
        self._created_at = datetime.now(timezone.utc)
        self._last_active_at: Optional[datetime] = None
        self._task_records: list[OhMyPiTaskRecord] = []
        self._lifecycle_history: list[tuple] = []

    @property
    def agent_id(self) -> str: return self._agent_id
    @property
    def status(self) -> AgentStatus: return self._status
    @property
    def profile(self) -> OhMyPiProfile: return self._profile
    @property
    def is_available(self) -> bool: return self._status == AgentStatus.READY
    @property
    def success_rate(self) -> float:
        if self._total_tasks == 0: return 100.0
        return round(self._successful_tasks / self._total_tasks * 100, 1)

    @property
    def agent_capabilities(self) -> list[AgentCapability]:
        return [c for cn in self._profile.capabilities if (c := self._cap(cn))]

    def _cap(self, name: str) -> Optional[AgentCapability]:
        try: return AgentCapability(name)
        except ValueError: return None

    def transition(self, target: AgentStatus, reason: str = "") -> bool:
        valid = {
            AgentStatus.CREATED: [AgentStatus.STARTING, AgentStatus.STOPPED],
            AgentStatus.STARTING: [AgentStatus.READY, AgentStatus.FAILED],
            AgentStatus.READY: [AgentStatus.BUSY, AgentStatus.PAUSED, AgentStatus.STOPPED, AgentStatus.FAILED],
            AgentStatus.BUSY: [AgentStatus.READY, AgentStatus.FAILED],
            AgentStatus.PAUSED: [AgentStatus.READY, AgentStatus.STOPPED],
            AgentStatus.FAILED: [AgentStatus.RECOVERING, AgentStatus.STOPPED],
            AgentStatus.RECOVERING: [AgentStatus.READY, AgentStatus.FAILED],
            AgentStatus.STOPPED: [],
        }
        if target not in valid.get(self._status, []):
            return False
        old = self._status
        self._status = target
        self._last_active_at = datetime.now(timezone.utc)
        self._lifecycle_history.append((old, target, reason, datetime.now(timezone.utc)))
        if target == AgentStatus.READY:
            self._publish(OHMYPI_EVENTS["agent_ready"], {"agent_id": self._agent_id})
        return True

    def start(self) -> bool:
        return self.transition(AgentStatus.STARTING, "starting") and self.transition(AgentStatus.READY, "ready")
    def stop(self) -> bool:
        return self._status == AgentStatus.STOPPED or self.transition(AgentStatus.STOPPED, "stopping")
    def mark_busy(self, task_id: str = "") -> bool:
        self._current_task_id = task_id
        return self.transition(AgentStatus.BUSY, f"Task: {task_id}")
    def mark_ready(self) -> bool:
        self._current_task_id = ""
        return self.transition(AgentStatus.READY, "done")

    def execute_task(self, task_type: str, parameters: dict[str, Any],
                     mission_id: str = "", node_id: str = "",
                     agent_id_override: str = "") -> ExecutionResult:
        agent = agent_id_override or self._agent_id
        started = datetime.now(timezone.utc)
        mcp_action = TASK_TO_MCP_ACTION.get(task_type, task_type)

        # Workspace protection for write operations
        if task_type in (OhMyPiTaskType.CODE_EDITING, OhMyPiTaskType.AST_MANIPULATION):
            ws_id = parameters.get("workspace_id", "")
            if self._workspace_manager and not ws_id:
                return ExecutionResult(context_id=node_id, agent_id=agent, node_id=node_id or "",
                                       outcome=TaskOutcome.FAILURE, started_at=started,
                                       completed_at=datetime.now(timezone.utc), duration_ms=0.0,
                                       summary="Write operations require workspace_id",
                                       error_message="Workspace required for edits")

        # Events
        if task_type == OhMyPiTaskType.CODE_EDITING:
            self._publish(OHMYPI_EVENTS["edit_started"], {"task_type": task_type, "agent_id": agent})
        elif task_type == OhMyPiTaskType.DEBUGGING:
            self._publish(OHMYPI_EVENTS["debug_started"], {"task_type": task_type, "agent_id": agent})

        self.mark_busy(task_id=node_id)
        success = False; error_msg = ""; data = None
        try:
            if self._mcp_adapter:
                response = self._mcp_adapter.execute(action=mcp_action, parameters=parameters,
                                                      agent_id=agent, mission_id=mission_id)
                success = response.status.value == "success"
                error_msg = response.error
                data = response.data
            else:
                # No adapter bound means the work did not happen. This used to
                # set success = True with {"status": "simulated"}, so a mission
                # with no Oh My Pi wired reported every task as succeeding
                # (R-002 P5).
                success = False
                error_msg = "Oh My Pi MCP adapter is not bound; task not executed"
                data = None
        except Exception as e:
            success = False; error_msg = str(e)

        completed = datetime.now(timezone.utc)
        duration_ms = (completed - started).total_seconds() * 1000

        if success:
            if task_type == OhMyPiTaskType.CODE_EDITING:
                self._publish(OHMYPI_EVENTS["edit_completed"], {"duration_ms": duration_ms})
            elif task_type == OhMyPiTaskType.CODE_EXECUTION:
                self._publish(OHMYPI_EVENTS["execution_completed"], {"duration_ms": duration_ms})
        else:
            self._publish(OHMYPI_EVENTS["error"], {"error": error_msg}, "error")

        with self._lock:
            self._total_tasks += 1; self._total_duration_ms += duration_ms
            if success: self._successful_tasks += 1
            else: self._failed_tasks += 1
            self._last_active_at = completed

        self._task_records.append(OhMyPiTaskRecord(
            task_id=node_id or f"t_{int(time.time())}", task_type=task_type,
            result="success" if success else "failure", duration_ms=duration_ms,
            errors=[error_msg] if error_msg else [], mcp_action=mcp_action,
            agent_id=agent, mission_id=mission_id))
        if len(self._task_records) > 500:
            self._task_records = self._task_records[-500:]

        self.mark_ready()
        return ExecutionResult(context_id=node_id, agent_id=agent, node_id=node_id or "",
                               outcome=TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE,
                               started_at=started, completed_at=completed, duration_ms=duration_ms,
                               summary=f"OhMyPi {task_type}: {'ok' if success else 'fail'}",
                               details={"data": data, "mcp_action": mcp_action},
                               error_message=error_msg)

    def to_agent_dataclass(self) -> Agent:
        profile = AgentProfile(
            max_concurrent_tasks=self._profile.max_concurrent_tasks,
            max_retries=self._profile.max_retries,
            timeout_seconds=self._profile.timeout_seconds,
            skill_levels=self._profile.skill_levels,
            preferred_task_types=self._profile.preferred_task_types,
            reliability_score=self._profile.reliability_score,
            performance_score=self._profile.performance_score,
            tags=self._profile.tags,
        )
        return Agent(agent_id=self._agent_id, name=self._profile.agent_name,
                     description=self._profile.agent_description, status=self._status,
                     capabilities=self.agent_capabilities, profile=profile,
                     preferred_runtime="ohmypi", total_tasks=self._total_tasks,
                     successful_tasks=self._successful_tasks, failed_tasks=self._failed_tasks,
                     total_duration_ms=self._total_duration_ms,
                     created_at=self._created_at, last_active_at=self._last_active_at,
                     metadata={"agent_type": "ohmypi", "mcp_tools": self._profile.mcp_tools})

    def get_metrics(self) -> AgentMetrics:
        return AgentMetrics(agent_id=self._agent_id, total_tasks=self._total_tasks,
                            successful_tasks=self._successful_tasks, failed_tasks=self._failed_tasks,
                            avg_duration_ms=self._total_duration_ms / max(self._total_tasks, 1),
                            success_rate=self.success_rate, last_active=self._last_active_at)

    def get_status_dict(self) -> dict:
        return {"agent_id": self._agent_id, "name": self._profile.agent_name,
                "status": self._status.value, "is_available": self.is_available,
                "capabilities": [c.value for c in self.agent_capabilities],
                "mcp_tools": self._profile.mcp_tools,
                "total_tasks": self._total_tasks, "success_rate": self.success_rate}

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event:
            try: self._on_event(event_type, payload, severity=severity)
            except Exception: pass


def create_ohmypi_agent(on_event: Optional[Callable] = None, mcp_adapter: Any = None,
                         memory_manager: Any = None, workspace_manager: Any = None) -> OhMyPiAgent:
    agent = OhMyPiAgent(on_event=on_event, mcp_adapter=mcp_adapter,
                         memory_manager=memory_manager, workspace_manager=workspace_manager)
    agent.start()
    return agent
