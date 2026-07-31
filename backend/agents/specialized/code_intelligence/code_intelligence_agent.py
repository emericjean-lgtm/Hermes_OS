"""Code Intelligence Agent (HOS-055D).

Meta-agent that intelligently routes code tasks between KlaatCode and Oh My Pi.
It analyzes each task, scores both providers, and selects the optimal execution
strategy — single-best or hybrid.

Integrates with:
- Agent Supervisor HOS-043: lifecycle, capability matching, task dispatch
- Code Intelligence Router HOS-055D: scoring, routing decisions
- KlaatCodeAgent HOS-054C: project analysis, diagnostics, code review
- OhMyPiAgent HOS-055B: LSP/DAP/AST editing, debugging, execution
- Execution Engine HOS-050: Mission DAG, task scheduling
- Event Bus: publishes ci.* events
- Memory System HOS-047: records experiences with provider attribution

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
    ExecutionResult,
    TaskOutcome,
)
from backend.integrations.code_intelligence.code_intelligence_models import (
    CodeIntelligenceTask,
    CodeIntelligenceTaskType,
    CodeProvider,
    HybridExecutionResult,
    ProviderExecutionResult,
    RouteReason,
    RoutingDecision,
    SelectionStrategy,
)
from backend.integrations.code_intelligence.code_intelligence_router import (
    CodeIntelligenceRouter,
)

from .capabilities import CI_EVENTS, CICapability, CodeIntelligenceAgentStatus
from .profile import CodeIntelligenceProfile


# ── Data classes ─────────────────────────────────────────────

@dataclass
class CITaskRecord:
    """Record of a routed task for memory and analytics."""
    task_id: str = ""
    task_type: str = ""
    selected_provider: str = ""
    strategy: str = ""
    primary_reason: str = ""
    success: bool = False
    duration_ms: float = 0.0
    klaatcode_score: float = 0.0
    ohmypi_score: float = 0.0
    errors: list[str] = field(default_factory=list)
    mission_id: str = ""
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── CodeIntelligenceAgent ────────────────────────────────────

class CodeIntelligenceAgent:
    """Meta-agent that routes code tasks to KlaatCode or Oh My Pi.

    This agent does NOT extend BaseAgent — it is a pure orchestrator
    that delegates actual work to specialized sub-agents.
    """

    def __init__(
        self,
        agent_id: str = "",
        on_event: Optional[Callable] = None,
        klaatcode_agent: Any = None,
        ohmypi_agent: Any = None,
        router: Optional[CodeIntelligenceRouter] = None,
        memory_manager: Any = None,
        agent_coordinator: Any = None,
    ) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._klaatcode_agent = klaatcode_agent
        self._ohmypi_agent = ohmypi_agent
        self._router = router or CodeIntelligenceRouter()
        self._memory_manager = memory_manager
        self._agent_coordinator = agent_coordinator

        # Profile
        self._profile = CodeIntelligenceProfile()

        # Identity
        if not agent_id:
            import uuid
            agent_id = f"ci_{uuid.uuid4().hex[:8]}"
        self._agent_id = agent_id

        # Status
        self._status = AgentStatus.CREATED
        self._op_status = CodeIntelligenceAgentStatus.IDLE

        # Task tracking
        self._current_task_id: str = ""
        self._current_mission_id: str = ""
        self._task_records: list[CITaskRecord] = []

        # Metrics
        self._total_tasks = 0
        self._successful_tasks = 0
        self._failed_tasks = 0
        self._total_duration_ms = 0.0
        self._created_at = datetime.now(timezone.utc)
        self._last_active_at: Optional[datetime] = None

        # Provider-specific metrics
        self._klaatcode_tasks = 0
        self._ohmypi_tasks = 0
        self._hybrid_tasks = 0

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
    def op_status(self) -> CodeIntelligenceAgentStatus:
        with self._lock:
            return self._op_status

    @property
    def profile(self) -> CodeIntelligenceProfile:
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
            return 1.0 if self._op_status != CodeIntelligenceAgentStatus.IDLE else 0.0

    @property
    def agent_capabilities(self) -> list[AgentCapability]:
        caps = []
        for cname in self._profile.capabilities:
            try:
                caps.append(AgentCapability(cname))
            except ValueError:
                pass
        return caps

    # ── Lifecycle ────────────────────────────────────────────

    def transition(self, target: AgentStatus, reason: str = "") -> bool:
        with self._lock:
            old = self._status
            valid = {
                AgentStatus.CREATED: [AgentStatus.STARTING, AgentStatus.STOPPED],
                AgentStatus.STARTING: [AgentStatus.READY, AgentStatus.FAILED],
                AgentStatus.READY: [AgentStatus.BUSY, AgentStatus.PAUSED, AgentStatus.STOPPED, AgentStatus.FAILED],
                AgentStatus.BUSY: [AgentStatus.READY, AgentStatus.FAILED],
                AgentStatus.PAUSED: [AgentStatus.READY, AgentStatus.STOPPED],
                AgentStatus.FAILED: [AgentStatus.STOPPED],
                AgentStatus.STOPPED: [],
            }
            if target not in valid.get(old, []):
                return False
            self._status = target
            self._last_active_at = datetime.now(timezone.utc)
            self._lifecycle_history.append((old, target, reason, datetime.now(timezone.utc)))
            if target == AgentStatus.READY:
                self._op_status = CodeIntelligenceAgentStatus.IDLE
            elif target == AgentStatus.STOPPED:
                self._op_status = CodeIntelligenceAgentStatus.IDLE
        if target == AgentStatus.READY and self._on_event:
            self._publish(CI_EVENTS["agent_ready"], {"agent_id": self._agent_id})
        return True

    def start(self) -> bool:
        if not self.transition(AgentStatus.STARTING, "Starting CI agent"):
            return False
        return self.transition(AgentStatus.READY, "Code Intelligence agent ready")

    def stop(self) -> bool:
        if self._status == AgentStatus.STOPPED:
            return True
        return self.transition(AgentStatus.STOPPED, "Stopping CI agent")

    def pause(self) -> bool:
        return self.transition(AgentStatus.PAUSED, "Pausing")

    def resume(self) -> bool:
        return self.transition(AgentStatus.READY, "Resuming")

    def mark_busy(self, task_id: str = "") -> bool:
        with self._lock:
            self._current_task_id = task_id
        return self.transition(AgentStatus.BUSY, f"Task: {task_id}")

    def mark_ready(self) -> bool:
        with self._lock:
            self._current_task_id = ""
        return self.transition(AgentStatus.READY, "Task complete")

    # ── Core: Execute Task ───────────────────────────────────

    def execute_task(
        self,
        task_type: str,
        parameters: dict[str, Any],
        mission_id: str = "",
        node_id: str = "",
        force_provider: CodeProvider | None = None,
    ) -> ExecutionResult:
        """Execute a code task by routing to the best provider.

        Pipeline:
        1. Classify task → CodeIntelligenceTask
        2. Score both providers → RoutingDecision
        3. Execute via selected provider(s)
        4. Record result → Memory + EventBus
        5. Update metrics
        """
        started = datetime.now(timezone.utc)
        agent = self._agent_id

        # 1. Classify
        try:
            ci_task_type = CodeIntelligenceTaskType(task_type)
        except ValueError:
            ci_task_type = CodeIntelligenceTaskType.CODE_ANALYSIS

        ci_task = CodeIntelligenceTask(
            task_id=node_id or f"ci_{int(time.time())}",
            task_type=ci_task_type,
            language=parameters.get("language", ""),
            project_path=parameters.get("project_path", "."),
            complexity=float(parameters.get("complexity", 0.5)),
            parameters=parameters,
            requires_lsp=bool(parameters.get("requires_lsp", False)),
            requires_dap=bool(parameters.get("requires_dap", False)),
            requires_ast=bool(parameters.get("requires_ast", False)),
            requires_execution=bool(parameters.get("requires_execution", False)),
            mission_id=mission_id,
            node_id=node_id,
            agent_id=agent,
        )

        # 2. Route
        kc_available = self._klaatcode_agent is not None
        omp_available = self._ohmypi_agent is not None

        decision = self._router.decide(
            ci_task,
            klaatcode_available=kc_available,
            ohmypi_available=omp_available,
            force_provider=force_provider,
        )
        self._publish(CI_EVENTS["routing_decided"], {
            "decision": decision.to_dict(),
            "task_type": task_type,
        })

        self.mark_busy(task_id=node_id)

        # 3. Execute
        if decision.strategy == SelectionStrategy.HYBRID_BOTH:
            self._op_status = CodeIntelligenceAgentStatus.EXECUTING_HYBRID
            hybrid_result = self._router.execute_hybrid(
                ci_task, self._klaatcode_agent, self._ohmypi_agent,
                order=decision.hybrid_order,
            )
            success = hybrid_result.overall_success
            data = hybrid_result.merged_data
            errors = hybrid_result.errors
            duration_ms = hybrid_result.total_duration_ms
            self._publish(CI_EVENTS["hybrid_executed"], {
                "success": success, "errors": errors, "duration_ms": duration_ms,
            })
        else:
            provider = decision.selected_provider
            if provider == CodeProvider.KLATCODE:
                self._op_status = CodeIntelligenceAgentStatus.EXECUTING_KLATCODE
                executor = self._klaatcode_agent
            else:
                self._op_status = CodeIntelligenceAgentStatus.EXECUTING_OHMYPI
                executor = self._ohmypi_agent

            if executor:
                try:
                    result = executor.execute_task(
                        task_type, parameters,
                        mission_id=mission_id, node_id=node_id,
                    )
                    success = result.outcome == TaskOutcome.SUCCESS
                    data = result.details.get("data") if result.details else None
                    errors = [result.error_message] if result.error_message else []
                    duration_ms = result.duration_ms
                except Exception as e:
                    success = False
                    data = None
                    errors = [str(e)]
                    duration_ms = 0.0
            else:
                # No provider bound means the work did not happen. This used to
                # set success = True with {"status": "simulated"}, so routing to
                # an unavailable provider still reported a completed task
                # (R-002 P5).
                success = False
                data = None
                errors = [f"provider {provider.value} is not bound; task not executed"]
                duration_ms = 0.0

        completed = datetime.now(timezone.utc)
        total_duration = (completed - started).total_seconds() * 1000

        # 4. Record
        self._router.record_result(
            decision.selected_provider, success, task_type
        )

        record = CITaskRecord(
            task_id=ci_task.task_id,
            task_type=task_type,
            selected_provider=decision.selected_provider.value,
            strategy=decision.strategy.value,
            primary_reason=decision.primary_reason.value,
            success=success,
            duration_ms=duration_ms or total_duration,
            klaatcode_score=decision.metadata.get("klaatcode_score", 0),
            ohmypi_score=decision.metadata.get("ohmypi_score", 0),
            errors=errors,
            mission_id=mission_id,
            agent_id=agent,
        )
        with self._lock:
            self._task_records.append(record)
            if len(self._task_records) > 500:
                self._task_records = self._task_records[-500:]

        # Memory
        self._record_to_memory(record)

        # Metrics
        with self._lock:
            self._total_tasks += 1
            self._total_duration_ms += total_duration
            if success:
                self._successful_tasks += 1
            else:
                self._failed_tasks += 1
            if decision.strategy == SelectionStrategy.HYBRID_BOTH:
                self._hybrid_tasks += 1
            elif decision.selected_provider == CodeProvider.KLATCODE:
                self._klaatcode_tasks += 1
            elif decision.selected_provider == CodeProvider.OHMYPI:
                self._ohmypi_tasks += 1
            self._last_active_at = completed

        # Events
        ev = CI_EVENTS["task_completed"] if success else CI_EVENTS["task_failed"]
        self._publish(ev, {
            "task_type": task_type,
            "provider": decision.selected_provider.value,
            "strategy": decision.strategy.value,
            "success": success,
            "duration_ms": duration_ms or total_duration,
            "errors": errors,
        }, severity="info" if success else "error")

        self.mark_ready()

        return ExecutionResult(
            context_id=node_id,
            agent_id=agent,
            node_id=node_id or "",
            outcome=TaskOutcome.SUCCESS if success else TaskOutcome.FAILURE,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms or total_duration,
            summary=f"CI {task_type}: {decision.selected_provider.value} {'success' if success else 'failed'}",
            details={
                "data": data,
                "provider": decision.selected_provider.value,
                "strategy": decision.strategy.value,
                "decision": decision.to_dict(),
            },
            error_message=errors[0] if errors else "",
        )

    # ── Memory ────────────────────────────────────────────────

    def _record_to_memory(self, record: CITaskRecord) -> None:
        if self._memory_manager is None:
            return
        try:
            from backend.memory.memory_models import EpisodicMemory
            episode = EpisodicMemory(
                episode_id=f"ci_{record.task_id}",
                mission_id=record.mission_id or "",
                mission_title=f"CI {record.task_type} via {record.selected_provider}",
                mission_type=record.task_type,
                success=record.success,
                total_nodes=1,
                completed_nodes=1 if record.success else 0,
                failed_nodes=0 if record.success else 1,
                duration_seconds=record.duration_ms / 1000.0,
                agents_used=[self._agent_id, f"provider:{record.selected_provider}"],
                tags=["code_intelligence", record.task_type, record.selected_provider],
                lessons_learned=[
                    f"Routed {record.task_type} to {record.selected_provider} "
                    f"({record.strategy}, reason: {record.primary_reason})"
                ],
                improvements=[],
            )
            self._memory_manager.record_episode(episode)
            self._publish(CI_EVENTS["recorded_to_memory"], {
                "task_id": record.task_id,
                "provider": record.selected_provider,
            })
        except Exception:
            pass

    # ── Agent Supervisor compatibility ────────────────────────

    def to_agent_dataclass(self) -> Agent:
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
            preferred_runtime="code_intelligence",
            preferred_model="",
            benchmark_profile="code_intelligence",
            current_task_id=self._current_task_id,
            current_mission_id=self._current_mission_id,
            total_tasks=self._total_tasks,
            successful_tasks=self._successful_tasks,
            failed_tasks=self._failed_tasks,
            total_duration_ms=self._total_duration_ms,
            created_at=self._created_at,
            last_active_at=self._last_active_at,
            metadata={
                "agent_type": "code_intelligence",
                "op_status": self._op_status.value,
                "providers": self._profile.providers,
                "klaatcode_tasks": self._klaatcode_tasks,
                "ohmypi_tasks": self._ohmypi_tasks,
                "hybrid_tasks": self._hybrid_tasks,
            },
        )

    # ── Stats ─────────────────────────────────────────────────

    def get_metrics(self) -> AgentMetrics:
        with self._lock:
            avg_dur = self._total_duration_ms / max(self._total_tasks, 1)
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
                "providers": self._profile.providers,
                "total_tasks": self._total_tasks,
                "successful_tasks": self._successful_tasks,
                "failed_tasks": self._failed_tasks,
                "klaatcode_tasks": self._klaatcode_tasks,
                "ohmypi_tasks": self._ohmypi_tasks,
                "hybrid_tasks": self._hybrid_tasks,
                "success_rate": self.success_rate,
                "router_stats": self._router.stats(),
                "current_task_id": self._current_task_id,
            }

    def get_task_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            records = self._task_records[-limit:]
            return [
                {
                    "task_id": r.task_id,
                    "task_type": r.task_type,
                    "selected_provider": r.selected_provider,
                    "strategy": r.strategy,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                    "kc_score": r.klaatcode_score,
                    "omp_score": r.ohmypi_score,
                    "primary_reason": r.primary_reason,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in records
            ]

    def get_lifecycle_history(self) -> list[dict]:
        with self._lock:
            return [
                {"from": o.value, "to": n.value, "reason": r, "ts": ts.isoformat()}
                for o, n, r, ts in self._lifecycle_history
            ]

    # ── Helpers ───────────────────────────────────────────────

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, payload, severity=severity)
        except Exception:
            pass


# ── Factory ──────────────────────────────────────────────────

def create_code_intelligence_agent(
    on_event: Optional[Callable] = None,
    klaatcode_agent: Any = None,
    ohmypi_agent: Any = None,
    router: Optional[CodeIntelligenceRouter] = None,
    memory_manager: Any = None,
    agent_coordinator: Any = None,
) -> CodeIntelligenceAgent:
    """Factory to create and start a CodeIntelligenceAgent."""
    agent = CodeIntelligenceAgent(
        on_event=on_event,
        klaatcode_agent=klaatcode_agent,
        ohmypi_agent=ohmypi_agent,
        router=router,
        memory_manager=memory_manager,
        agent_coordinator=agent_coordinator,
    )
    agent.start()
    return agent
