"""KlaatCode Agent (HOS-054C).

Specialized coding agent that uses KlaatCode MCP tools for code analysis,
generation, editing, refactoring, diagnostics, test analysis, project
navigation, patch generation, and code review.

Integrates with:
- Agent Supervisor HOS-043: full lifecycle, capability matching, task dispatch
- MCP Tools HOS-054B: analyze_project, inspect_code, generate_code_plan, etc.
- Execution Engine HOS-050: task scheduling, agent coordination, validation
- Event Bus HOS-034: publishes klaatcode.agent.* and klaatcode.task.* events
- Memory System HOS-047: records episodic memory, feeds experience manager

Thread-safe.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentMetrics,
    AgentProfile,
    AgentStatus,
    ExecutionContext,
    ExecutionResult,
    TaskOutcome,
)

from .klaatcode_capabilities import (
    KlaatCodeAgentStatus,
    KlaatCodeTaskType,
    TASK_TO_CAPABILITY,
    TASK_TO_MCP_ACTION,
)
from .klaatcode_profile import KlaatCodeProfile


# ── Event types ──────────────────────────────────────────────

KLATCODE_EVENTS = {
    "agent_ready": "klaatcode.agent.ready",
    "task_started": "klaatcode.task.started",
    "task_completed": "klaatcode.task.completed",
    "task_failed": "klaatcode.task.failed",
    "analysis_completed": "klaatcode.analysis.completed",
    "patch_generated": "klaatcode.patch.generated",
}


# ── Data classes ─────────────────────────────────────────────

@dataclass
class KlaatCodeTaskRecord:
    """Record of a completed KlaatCode task for memory storage."""

    task_id: str = ""
    task_type: str = ""
    language: str = ""
    project: str = ""
    difficulty: float = 0.0
    result: str = ""  # success / failure / timeout
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    mcp_action: str = ""
    agent_id: str = ""
    mission_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── KlaatCodeAgent ───────────────────────────────────────────

class KlaatCodeAgent:
    """Specialized coding agent backed by KlaatCode MCP tools.

    This agent is designed to be registered with the AgentSupervisor (HOS-043)
    and participates fully in the multi-agent task dispatch pipeline.

    It does NOT extend BaseAgent — KlaatCode runs locally without an LLM.
    """

    def __init__(
        self,
        agent_id: str = "",
        on_event: Optional[Callable] = None,
        mcp_adapter: Any = None,
        memory_manager: Any = None,
        agent_coordinator: Any = None,
        workspace_manager: Any = None,
        code_graph_adapter: Any = None,
        diagnostics_adapter: Any = None,
        cost_guard_adapter: Any = None,
    ) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._mcp_adapter = mcp_adapter
        self._memory_manager = memory_manager
        self._agent_coordinator = agent_coordinator
        self._workspace_manager = workspace_manager
        self._code_graph = code_graph_adapter
        self._diagnostics = diagnostics_adapter
        self._cost_guard = cost_guard_adapter

        # Profile
        self._profile = KlaatCodeProfile()

        # Agent identity
        if not agent_id:
            import uuid
            agent_id = f"klaatcode_{uuid.uuid4().hex[:8]}"
        self._agent_id = agent_id

        # Status
        self._status = AgentStatus.CREATED
        self._op_status = KlaatCodeAgentStatus.IDLE

        # Task tracking
        self._current_task_id: str = ""
        self._current_mission_id: str = ""
        self._task_queue: deque[KlaatCodeTaskRecord] = deque(maxlen=500)
        self._execution_history: list[ExecutionResult] = []
        self._task_records: list[KlaatCodeTaskRecord] = []

        # Metrics
        self._total_tasks = 0
        self._successful_tasks = 0
        self._failed_tasks = 0
        self._total_duration_ms = 0.0
        self._created_at = datetime.now(timezone.utc)
        self._last_active_at: Optional[datetime] = None

        # Lifecycle history
        self._lifecycle_history: list[tuple[AgentStatus, AgentStatus, str, datetime]] = []

    # ── Properties ───────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def status(self) -> AgentStatus:
        with self._lock:
            return self._status

    @property
    def op_status(self) -> KlaatCodeAgentStatus:
        with self._lock:
            return self._op_status

    @property
    def profile(self) -> KlaatCodeProfile:
        return self._profile

    @property
    def is_available(self) -> bool:
        with self._lock:
            return self._status == AgentStatus.READY

    @property
    def success_rate(self) -> float:
        with self._lock:
            if self._total_tasks == 0:
                return 100.0
            return round(self._successful_tasks / self._total_tasks * 100, 1)

    @property
    def load(self) -> float:
        with self._lock:
            return 1.0 if (self._op_status != KlaatCodeAgentStatus.IDLE or self._status == AgentStatus.BUSY) else 0.0

    @property
    def agent_capabilities(self) -> list[AgentCapability]:
        """Return AgentCapability enums for registry matching."""
        caps = []
        for cname in self._profile.capabilities:
            try:
                caps.append(AgentCapability(cname))
            except ValueError:
                pass
        return caps

    # ── Lifecycle ────────────────────────────────────────────

    def transition(
        self, target: AgentStatus, reason: str = ""
    ) -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._lock:
            old = self._status

            # Validate transition
            valid = {
                AgentStatus.CREATED: [AgentStatus.STARTING, AgentStatus.STOPPED],
                AgentStatus.STARTING: [AgentStatus.READY, AgentStatus.FAILED],
                AgentStatus.READY: [AgentStatus.BUSY, AgentStatus.PAUSED, AgentStatus.STOPPED, AgentStatus.FAILED],
                AgentStatus.BUSY: [AgentStatus.READY, AgentStatus.FAILED],
                AgentStatus.PAUSED: [AgentStatus.READY, AgentStatus.STOPPED],
                AgentStatus.FAILED: [AgentStatus.RECOVERING, AgentStatus.STOPPED],
                AgentStatus.RECOVERING: [AgentStatus.READY, AgentStatus.FAILED],
                AgentStatus.COMPLETED: [AgentStatus.STOPPED],
                AgentStatus.STOPPED: [],
            }
            if target not in valid.get(old, []):
                return False

            self._status = target
            self._last_active_at = datetime.now(timezone.utc)
            self._lifecycle_history.append((old, target, reason, datetime.now(timezone.utc)))

            # Map to operational status
            if target == AgentStatus.READY:
                self._op_status = KlaatCodeAgentStatus.IDLE
            elif target == AgentStatus.STOPPED:
                self._op_status = KlaatCodeAgentStatus.IDLE

        # Emit event
        event_map = {
            AgentStatus.READY: (KLATCODE_EVENTS["agent_ready"], "info"),
            AgentStatus.FAILED: (KLATCODE_EVENTS["task_failed"], "error"),
        }
        if target in event_map and self._on_event:
            ev_type, sev = event_map[target]
            self._on_event(ev_type, {
                "agent_id": self._agent_id,
                "name": self._profile.agent_name,
                "previous": old.value,
                "new": target.value,
                "reason": reason,
            }, severity=sev)

        return True

    def start(self) -> bool:
        """Start: CREATED → STARTING → READY."""
        if not self.transition(AgentStatus.STARTING, "Starting KlaatCode agent"):
            return False
        return self.transition(AgentStatus.READY, "KlaatCode agent ready")

    def stop(self) -> bool:
        """Stop the agent."""
        if self._status == AgentStatus.STOPPED:
            return True
        return self.transition(AgentStatus.STOPPED, "Stopping KlaatCode agent")

    def pause(self) -> bool:
        return self.transition(AgentStatus.PAUSED, "Pausing")

    def resume(self) -> bool:
        return self.transition(AgentStatus.READY, "Resuming")

    def mark_busy(self, task_id: str = "") -> bool:
        with self._lock:
            self._current_task_id = task_id
            self._op_status = KlaatCodeAgentStatus.ANALYZING  # non-IDLE indicator
        return self.transition(AgentStatus.BUSY, f"Task assigned: {task_id}")

    def mark_ready(self) -> bool:
        with self._lock:
            self._current_task_id = ""
        return self.transition(AgentStatus.READY, "Task completed")

    # ── Task Execution ───────────────────────────────────────

    def execute_task(
        self,
        task_type: str,
        parameters: dict[str, Any],
        mission_id: str = "",
        node_id: str = "",
        agent_id_override: str = "",
    ) -> ExecutionResult:
        """Execute a KlaatCode task through the MCP adapter pipeline.

        Args:
            task_type: One of KlaatCodeTaskType values or raw task type.
            parameters: Task-specific parameters (file paths, content, etc.).
            mission_id: Parent mission.
            node_id: MissionGraph node.
            agent_id_override: For dispatcher compatibility.

        Returns:
            ExecutionResult with outcome, timing, and details.
        """
        agent = agent_id_override or self._agent_id
        started = datetime.now(timezone.utc)

        # Map task type to MCP action
        mcp_action = TASK_TO_MCP_ACTION.get(task_type, task_type)

        # Emit task started event
        self._publish_event(
            KLATCODE_EVENTS["task_started"],
            {
                "task_type": task_type,
                "mcp_action": mcp_action,
                "agent_id": agent,
                "mission_id": mission_id,
                "node_id": node_id,
            },
        )

        # Mark busy
        self.mark_busy(task_id=node_id)
        if task_type == KlaatCodeTaskType.CODE_ANALYSIS:
            self._op_status = KlaatCodeAgentStatus.ANALYZING
        elif task_type in (KlaatCodeTaskType.CODE_GENERATION, KlaatCodeTaskType.CODE_EDITING):
            self._op_status = KlaatCodeAgentStatus.GENERATING
        elif task_type == KlaatCodeTaskType.DIAGNOSTICS:
            self._op_status = KlaatCodeAgentStatus.DIAGNOSING
        elif task_type == KlaatCodeTaskType.CODE_REVIEW:
            self._op_status = KlaatCodeAgentStatus.REVIEWING

        # ── Workspace protection for file edits ──
        workspace_id = parameters.get("workspace_id", "")
        if task_type in (KlaatCodeTaskType.CODE_EDITING, KlaatCodeTaskType.REFACTORING,
                          KlaatCodeTaskType.PATCH_GENERATION):
            # Require workspace for write operations
            if self._workspace_manager and not workspace_id:
                return ExecutionResult(
                    context_id=node_id,
                    agent_id=agent,
                    node_id=node_id or "",
                    outcome=TaskOutcome.FAILURE,
                    started_at=started,
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=0.0,
                    summary="Write operations require a workspace_id",
                    error_message="Workspace protection: edit_file requires a workspace",
                )

            # Enforce workspace sandbox for edits
            if self._workspace_manager and workspace_id:
                ws = self._workspace_manager.get(workspace_id)
                if ws is None:
                    return ExecutionResult(
                        context_id=node_id, agent_id=agent, node_id=node_id or "",
                        outcome=TaskOutcome.FAILURE,
                        started_at=started,
                        completed_at=datetime.now(timezone.utc),
                        duration_ms=0.0,
                        summary=f"Workspace '{workspace_id}' not found",
                        error_message="Workspace protection: invalid workspace",
                    )

        # Execute via MCP adapter
        success = False
        error_msg = ""
        data = None

        try:
            if self._mcp_adapter:
                response = self._mcp_adapter.execute(
                    action=mcp_action,
                    parameters=parameters,
                    agent_id=agent,
                    mission_id=mission_id,
                )
                success = response.status.value == "success"
                error_msg = response.error
                data = response.data
            else:
                # Fallback: simulate execution for CI / no KlaatCode
                data = {"status": "simulated", "action": mcp_action}
                success = True

        except Exception as e:
            success = False
            error_msg = str(e)

        completed = datetime.now(timezone.utc)
        duration_ms = (completed - started).total_seconds() * 1000

        # Emit task completed/failed event
        if success:
            self._publish_event(
                KLATCODE_EVENTS["task_completed"],
                {
                    "task_type": task_type,
                    "mcp_action": mcp_action,
                    "duration_ms": duration_ms,
                    "data": data,
                },
            )
            # Specific events
            if task_type == KlaatCodeTaskType.CODE_ANALYSIS:
                self._publish_event(KLATCODE_EVENTS["analysis_completed"], {
                    "mcp_action": mcp_action, "duration_ms": duration_ms,
                })
            elif task_type == KlaatCodeTaskType.PATCH_GENERATION:
                self._publish_event(KLATCODE_EVENTS["patch_generated"], {
                    "mcp_action": mcp_action, "duration_ms": duration_ms,
                })
        else:
            self._publish_event(
                KLATCODE_EVENTS["task_failed"],
                {
                    "task_type": task_type,
                    "error": error_msg,
                    "duration_ms": duration_ms,
                },
                severity="error",
            )

        # Update metrics
        with self._lock:
            self._total_tasks += 1
            self._total_duration_ms += duration_ms
            if success:
                self._successful_tasks += 1
            else:
                self._failed_tasks += 1
            self._last_active_at = completed

        # Record task
        record = KlaatCodeTaskRecord(
            task_id=node_id or f"task_{int(time.time())}",
            task_type=task_type,
            language=parameters.get("language", ""),
            project=parameters.get("project", ""),
            difficulty=float(parameters.get("difficulty", 0.0)),
            result="success" if success else "failure",
            duration_ms=duration_ms,
            errors=[error_msg] if error_msg else [],
            corrections=[],
            mcp_action=mcp_action,
            agent_id=agent,
            mission_id=mission_id,
        )
        with self._lock:
            self._task_records.append(record)
            if len(self._task_records) > 500:
                self._task_records = self._task_records[-500:]

        # Record in memory system
        self._record_to_memory(record)

        # Mark ready
        self.mark_ready()

        result = ExecutionResult(
            context_id=node_id,
            agent_id=agent,
            node_id=node_id or "",
            outcome=TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            summary=f"KlaatCode {task_type}: {'success' if success else 'failed'}",
            details={"data": data, "mcp_action": mcp_action},
            error_message=error_msg,
        )

        with self._lock:
            self._execution_history.append(result)
            if len(self._execution_history) > 200:
                self._execution_history = self._execution_history[-200:]

        return result

    # ── Memory Integration ────────────────────────────────────

    def _record_to_memory(self, record: KlaatCodeTaskRecord) -> None:
        """Record task outcome in the Memory System (HOS-047).

        Stores: problem, solution, files modified, time, success/failure.
        Feeds: Episodic Memory, Procedural Memory, Experience Manager.
        """
        if self._memory_manager is None:
            return
        try:
            from backend.memory.memory_models import EpisodicMemory, ProceduralMemory

            # 1. Episodic memory
            episode = EpisodicMemory(
                episode_id=f"kc_{record.task_id}",
                mission_id=record.mission_id or "",
                mission_title=f"KlaatCode {record.task_type}",
                mission_type=record.task_type,
                success=record.result == "success",
                total_nodes=1,
                completed_nodes=1 if record.result == "success" else 0,
                failed_nodes=0 if record.result == "success" else 1,
                duration_seconds=record.duration_ms / 1000.0,
                agents_used=[record.agent_id],
                tags=[
                    "klaatcode", record.task_type,
                    f"language:{record.language}" if record.language else "",
                ],
                lessons_learned=[
                    f"Task {record.task_type}: {record.result} in {record.duration_ms:.0f}ms"
                ],
                improvements=[],
            )
            self._memory_manager.record_episode(episode)

            # 2. Procedural memory — record workflow for reuse
            if record.result == "success":
                try:
                    procedure = ProceduralMemory(
                        name=f"klaatcode_{record.task_type}",
                        description=f"KlaatCode {record.task_type} procedure",
                        category="workflow",
                        steps=[
                            f"Execute {record.mcp_action} on {record.project or 'project'}",
                            f"Verify result ({record.duration_ms:.0f}ms)",
                        ],
                        derived_from_missions=[record.mission_id] if record.mission_id else [],
                        success_rate=1.0,
                        usage_count=1,
                        tags=["klaatcode", record.task_type],
                    )
                    self._memory_manager.store_procedure(procedure)
                except Exception:
                    pass

        except Exception:
            pass

    # ── Advanced Memory: Experience-based recommendations ──

    def get_experience_recommendations(
        self, task_type: str, language: str = "", tags: Optional[list] = None
    ) -> dict:
        """Get recommendations based on past KlaatCode experiences.

        Returns recommendations like:
        'For a similar error, this solution worked X times.'
        """
        if self._memory_manager is None:
            return {"recommendations": [], "similar_episodes": 0}
        try:
            search_tags = ["klaatcode", task_type]
            if language:
                search_tags.append(f"language:{language}")
            if tags:
                search_tags.extend(tags)

            recs = self._memory_manager.recommend_for_mission(task_type, search_tags)
            return recs
        except Exception:
            return {"recommendations": [], "similar_episodes": 0}

    # ── For CapabilityMatcher / AgentSupervisor compatibility ─

    def to_agent_dataclass(self) -> Agent:
        """Convert to an Agent dataclass for use with AgentRegistry."""
        profile = AgentProfile(
            max_concurrent_tasks=self._profile.max_concurrent_tasks,
            max_retries=self._profile.max_retries,
            timeout_seconds=self._profile.timeout_seconds,
            skill_levels=self._profile.skill_levels,
            preferred_task_types=self._profile.preferred_task_types,
            excluded_task_types=self._profile.excluded_task_types,
            reliability_score=self._profile.reliability_score,
            performance_score=self._profile.performance_score,
            max_tokens_per_task=self._profile.max_tokens_per_task,
            requires_gpu=self._profile.requires_gpu,
            tags=self._profile.tags,
        )
        return Agent(
            agent_id=self._agent_id,
            name=self._profile.agent_name,
            description=self._profile.agent_description,
            status=self._status,
            capabilities=self.agent_capabilities,
            profile=profile,
            preferred_runtime="klaatcode",
            preferred_model="",
            benchmark_profile="code_analysis",
            current_task_id=self._current_task_id,
            current_mission_id=self._current_mission_id,
            total_tasks=self._total_tasks,
            successful_tasks=self._successful_tasks,
            failed_tasks=self._failed_tasks,
            total_duration_ms=self._total_duration_ms,
            created_at=self._created_at,
            last_active_at=self._last_active_at,
            metadata={
                "agent_type": "klaatcode",
                "op_status": self._op_status.value,
                "mcp_tools": self._profile.mcp_tools,
            },
        )

    # ── Stats ─────────────────────────────────────────────────

    def get_metrics(self) -> AgentMetrics:
        with self._lock:
            avg_dur = (
                self._total_duration_ms / max(self._total_tasks, 1)
            )
            return AgentMetrics(
                agent_id=self._agent_id,
                total_tasks=self._total_tasks,
                successful_tasks=self._successful_tasks,
                failed_tasks=self._failed_tasks,
                cancelled_tasks=0,
                avg_duration_ms=avg_dur,
                min_duration_ms=0.0,
                max_duration_ms=0.0,
                success_rate=self.success_rate,
                last_active=self._last_active_at,
                current_load=self.load,
            )

    def get_status_dict(self) -> dict:
        with self._lock:
            return {
                "agent_id": self._agent_id,
                "name": self._profile.agent_name,
                "status": self._status.value,
                "op_status": self._op_status.value,
                "is_available": self.is_available,
                "capabilities": [c.value for c in self.agent_capabilities],
                "mcp_tools": self._profile.mcp_tools,
                "total_tasks": self._total_tasks,
                "successful_tasks": self._successful_tasks,
                "failed_tasks": self._failed_tasks,
                "success_rate": self.success_rate,
                "current_task_id": self._current_task_id,
                "current_mission_id": self._current_mission_id,
                "created_at": self._created_at.isoformat(),
                "last_active_at": self._last_active_at.isoformat() if self._last_active_at else None,
            }

    def get_task_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            records = self._task_records[-limit:]
            return [
                {
                    "task_id": r.task_id,
                    "task_type": r.task_type,
                    "result": r.result,
                    "duration_ms": r.duration_ms,
                    "mcp_action": r.mcp_action,
                    "language": r.language,
                    "project": r.project,
                    "difficulty": r.difficulty,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in records
            ]

    def get_lifecycle_history(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "from": old.value,
                    "to": new.value,
                    "reason": reason,
                    "timestamp": ts.isoformat(),
                }
                for old, new, reason, ts in self._lifecycle_history
            ]

    # ── Helpers ───────────────────────────────────────────────

    def _publish_event(
        self, event_type: str, payload: dict, severity: str = "info"
    ) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass


# ── Factory ──────────────────────────────────────────────────

def create_klaatcode_agent(
    on_event: Optional[Callable] = None,
    mcp_adapter: Any = None,
    memory_manager: Any = None,
    agent_coordinator: Any = None,
    workspace_manager: Any = None,
    code_graph_adapter: Any = None,
    diagnostics_adapter: Any = None,
    cost_guard_adapter: Any = None,
) -> KlaatCodeAgent:
    """Factory function to create and start a KlaatCodeAgent.

    Returns a fully initialized and ready agent with all deep integrations.
    """
    agent = KlaatCodeAgent(
        on_event=on_event,
        mcp_adapter=mcp_adapter,
        memory_manager=memory_manager,
        agent_coordinator=agent_coordinator,
        workspace_manager=workspace_manager,
        code_graph_adapter=code_graph_adapter,
        diagnostics_adapter=diagnostics_adapter,
        cost_guard_adapter=cost_guard_adapter,
    )
    agent.start()
    return agent
