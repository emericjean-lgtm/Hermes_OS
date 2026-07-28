"""Hermes Agent Adapter (HOS-023).

The adapter bridges the Hermes OS abstractions (RAL, Agent, Memory,
Skills) with the existing Hermes Agent codebase — BaseAgent, EchoAgent,
ModelRouter, OllamaClient — without modifying any of them.

Every direct dependency on Hermes Agent is encapsulated here so that
the rest of the system interacts only through this adapter's public API.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ── Hermes OS abstractions (adapted FROM) ────────────────────────────
from backend.ral.capabilities import ChatCapability, ChatResponse, CapabilityInterface
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus

# ── Hermes Agent code (adapted TO) ───────────────────────────────────
from backend.agents.base_agent import BaseAgent
from backend.connectors.ollama_client import OllamaClientProtocol, OllamaUnavailableError
from backend.core.router import ModelRouter, RoutingDecision
from backend.memory.unified_memory import (
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    UnifiedMemory,
)
from backend.skills.orchestrator import (
    AdaptiveSkillOrchestrator,
    SkillDescriptor,
    SkillSelection,
    SkillSelectionStrategy,
)

# EchoAgent is imported lazily (TYPE_CHECKING) because it depends on
# ``datetime.UTC`` (Python ≥ 3.11) through backend.memory.episodic.
# The adapter works fine without it if ``echo_agent`` is not provided.
import typing as _typing
if _typing.TYPE_CHECKING:
    from backend.agents.echo import EchoAgent


# ======================================================================
# Exceptions
# ======================================================================


class HermesAgentError(Exception):
    """Raised when a Hermes Agent adapter operation fails."""


class HermesAgentNotConnectedError(HermesAgentError):
    """Raised when an operation is attempted without an active connection."""


class HermesAgentTaskError(HermesAgentError):
    """Raised when a task operation fails."""


# ======================================================================
# Enums
# ======================================================================


class HermesAgentStatus(str, Enum):
    """Connection status of the Hermes Agent adapter."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class HermesCapability(str, Enum):
    """Capabilities exposed by the Hermes Agent adapter.

    These are the RAL-level capabilities that the adapter maps to
    Hermes Agent's concrete abilities.
    """

    CHAT = "chat"
    CHAT_STREAM = "chat_stream"
    TOOLS = "tools"
    MEMORY = "memory"
    SKILLS = "skills"
    SUBAGENTS = "subagents"
    DELEGATION = "delegation"


# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class HermesAgentConfiguration:
    """Configuration for the Hermes Agent adapter.

    Attributes:
        base_url: Ollama API base URL (e.g. ``http://localhost:11434``).
        keep_alive: Model keep-alive duration string (e.g. ``"10m"``).
        timeout: HTTP client timeout in seconds.
        max_attempts: Maximum connection retry attempts.
        auto_reconnect: Whether to attempt reconnection on failure.
        default_sensitivity: Default generation sensitivity (``"standard"``,
            ``"safe"``, ``"critical"``).
    """

    base_url: str = "http://localhost:11434"
    keep_alive: str = "10m"
    timeout: float = 120.0
    max_attempts: int = 3
    auto_reconnect: bool = True
    default_sensitivity: str = "standard"


@dataclass(frozen=True)
class HermesAgentSession:
    """A conversation session with the Hermes Agent.

    Attributes:
        session_id: Unique session identifier.
        agent_name: Name of the agent handling this session.
        created_at: Timestamp of session creation.
        message_count: Number of messages exchanged.
        metadata: Free-form metadata.
    """

    session_id: str
    agent_name: str
    created_at: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HermesAgentTask:
    """A task submitted to the Hermes Agent for execution.

    Attributes:
        task_id: Unique task identifier.
        agent_name: Name of the agent executing this task.
        task_type: Type of task (e.g. ``"code"``, ``"chat"``).
        status: Current task status.
        messages: Messages associated with the task.
        created_at: Task creation timestamp.
        started_at: Task start timestamp (if started).
        finished_at: Task finish timestamp (if completed).
        routing_decision: The model routing decision for this task.
        result: Task result content (if completed).
        error: Error message (if failed).
        metadata: Free-form metadata.
    """

    task_id: str
    agent_name: str = ""
    task_type: str = "chat"
    status: str = "pending"
    messages: tuple[dict[str, Any], ...] = ()
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    routing_decision: Optional[RoutingDecision] = None
    result: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HermesAgentExecution:
    """Result of executing a task through the Hermes Agent.

    Attributes:
        task_id: The executed task's id.
        agent_name: Agent that executed the task.
        success: Whether execution succeeded.
        content: Response content.
        routing_decision: Model routing decision used.
        duration_ms: Execution duration in milliseconds.
        error: Error message if failed.
        metadata: Free-form metadata.
    """

    task_id: str
    agent_name: str
    success: bool
    content: str = ""
    routing_decision: Optional[RoutingDecision] = None
    duration_ms: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HermesAgentCapabilities:
    """Capabilities advertised by the Hermes Agent adapter.

    Attributes:
        available: Set of :class:`HermesCapability` values.
        models: List of available model tags from Ollama.
        agents: List of available Hermes Agent agent names.
    """

    available: frozenset[str]
    models: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()


# ======================================================================
# Adapter
# ======================================================================


class HermesAgentAdapter:
    """Bridges Hermes OS abstractions with the Hermes Agent codebase.

    The adapter encapsulates every direct dependency on Hermes Agent
    (BaseAgent, EchoAgent, ModelRouter, OllamaClient, etc.) behind a
    stable public API that the rest of the system can depend on.

    Construction requires no network call. Call :meth:`connect` before
    using any task-execution methods.

    Args:
        configuration: Adapter configuration.
        ollama_client: Pre-configured Ollama client (optional). If not
            provided, a client will be created on :meth:`connect`.
        model_router: Pre-configured model router (optional).
        agent: Pre-configured Hermes Agent instance (optional).
        memory: Hermes OS :class:`UnifiedMemory` instance (optional).
        skill_orchestrator: :class:`AdaptiveSkillOrchestrator` instance (optional).
        echo_agent: EchoAgent instance for Hermes Agent-native memory/skills.
    """

    def __init__(
        self,
        configuration: Optional[HermesAgentConfiguration] = None,
        *,
        ollama_client: Optional[OllamaClientProtocol] = None,
        model_router: Optional[ModelRouter] = None,
        agent: Optional[BaseAgent] = None,
        memory: Optional[UnifiedMemory] = None,
        skill_orchestrator: Optional[AdaptiveSkillOrchestrator] = None,
        echo_agent: Optional[EchoAgent] = None,
    ) -> None:
        self._config = configuration or HermesAgentConfiguration()
        self._ollama_client = ollama_client
        self._model_router = model_router
        self._agent = agent
        self._memory = memory or UnifiedMemory()
        self._skill_orchestrator = skill_orchestrator or AdaptiveSkillOrchestrator()
        self._echo_agent = echo_agent

        self._status: HermesAgentStatus = HermesAgentStatus.DISCONNECTED
        self._lock = threading.RLock()
        self._sessions: dict[str, HermesAgentSession] = {}
        self._tasks: dict[str, HermesAgentTask] = {}
        self._subagents: dict[str, str] = {}  # agent_name → type
        self._handlers: list[Callable] = []
        self._connect_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def status(self) -> HermesAgentStatus:
        return self._status

    async def connect(self) -> None:
        """Establish the connection to Hermes Agent infrastructure.

        Validates that the required components are available and that
        the Ollama endpoint is reachable.

        Raises:
            HermesAgentError: If connection fails or required components
                are missing.
        """
        with self._lock:
            self._status = HermesAgentStatus.CONNECTING

        try:
            # Validate / create the Ollama client.
            if self._ollama_client is None:
                from backend.connectors.ollama_client import OllamaClient

                self._ollama_client = OllamaClient(
                    base_url=self._config.base_url,
                    keep_alive=self._config.keep_alive,
                    timeout=self._config.timeout,
                    max_attempts=self._config.max_attempts,
                )

            # Validate / create the model router.
            if self._model_router is None:
                from backend.core.router import ModelRouter

                self._model_router = ModelRouter()

            # Validate / create the Hermes Agent.
            if self._agent is None:
                from backend.agents.prime import PrimeAgent

                models_config = {}
                try:
                    from backend.core.config import load_models_config
                    models_config = load_models_config()
                except Exception:
                    models_config = {"generation_defaults": {"standard": {}}}

                self._agent = PrimeAgent(
                    ollama_client=self._ollama_client,
                    router=self._model_router,
                    models_config=models_config,
                )

            # Ping Ollama to verify connectivity (soft check).
            try:
                await self._ollama_client.list_local_models()
            except Exception:
                if not self._config.auto_reconnect:
                    raise HermesAgentError(
                        f"Ollama is not reachable at {self._config.base_url}. "
                        "Check that it is running."
                    ) from None

            with self._lock:
                self._status = HermesAgentStatus.CONNECTED
                self._connect_time = time.time()

        except Exception as exc:
            with self._lock:
                self._status = HermesAgentStatus.ERROR
            raise HermesAgentError(f"Connection failed: {exc}") from exc

    async def disconnect(self) -> None:
        """Close the connection and release resources."""
        with self._lock:
            self._sessions.clear()
            self._tasks.clear()
            self._status = HermesAgentStatus.DISCONNECTED
            self._connect_time = None

    async def health(self) -> dict[str, Any]:
        """Check the health of the Hermes Agent adapter.

        Returns:
            A dict with ``status``, ``connected_since``, ``tasks``,
            ``sessions``, and ``ollama_status`` keys.
        """
        ollama_ok = False
        models_available = 0
        if self._status == HermesAgentStatus.CONNECTED and self._ollama_client is not None:
            try:
                models = await self._ollama_client.list_local_models()
                models_available = len(models)
                ollama_ok = True
            except Exception:
                ollama_ok = False

        return {
            "status": self._status.value,
            "connected_since": self._connect_time,
            "tasks_count": len(self._tasks),
            "sessions_count": len(self._sessions),
            "ollama_reachable": ollama_ok,
            "models_available": models_available,
            "subagents": len(self._subagents),
        }

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    async def get_capabilities(self) -> HermesAgentCapabilities:
        """List the capabilities exposed by this adapter.

        Returns:
            An agent capabilities descriptor with available models and
            agent names.
        """
        models: list[str] = []
        agents: list[str] = ["prime", "echo", "aegis"]

        if self._ollama_client is not None:
            try:
                local = await self._ollama_client.list_local_models()
                models = [m.get("name", "") for m in local if m.get("name")]
            except Exception:
                models = []

        initial = frozenset({
            HermesCapability.CHAT.value,
            HermesCapability.CHAT_STREAM.value,
            HermesCapability.TOOLS.value,
            HermesCapability.MEMORY.value,
            HermesCapability.SKILLS.value,
            HermesCapability.SUBAGENTS.value,
            HermesCapability.DELEGATION.value,
        })

        return HermesAgentCapabilities(
            available=initial,
            models=tuple(models),
            agents=tuple(agents),
        )

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def execute_task(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str = "chat",
        sensitivity: str | None = None,
        agent_name: str = "prime",
        metadata: Optional[dict[str, Any]] = None,
    ) -> HermesAgentExecution:
        """Execute a task through the Hermes Agent.

        This method:
          1. Asks the ModelRouter for the best model.
          2. Delegates to the Hermes Agent's ``respond()`` method.
          3. Collects the streamed response.
          4. Records the execution and routing decision.

        Args:
            messages: Conversation messages.
            task_type: Type of task (``"chat"``, ``"code"``, etc.).
            sensitivity: Generation sensitivity override.
            agent_name: Agent to use (``"prime"``, ``"echo"``, etc.).
            metadata: Optional execution metadata.

        Returns:
            An :class:`HermesAgentExecution` with the result.

        Raises:
            HermesAgentNotConnectedError: If the adapter is not connected.
            HermesAgentTaskError: If the task cannot be executed.
        """
        if self._status != HermesAgentStatus.CONNECTED:
            raise HermesAgentNotConnectedError(
                "Cannot execute task: adapter is not connected. "
                "Call connect() first."
            )

        if self._agent is None:
            raise HermesAgentTaskError(
                "No Hermes Agent instance available for task execution."
            )

        task_id = uuid.uuid4().hex
        sens = sensitivity or self._config.default_sensitivity
        start_time = time.monotonic()

        task = HermesAgentTask(
            task_id=task_id,
            agent_name=agent_name,
            task_type=task_type,
            status="running",
            messages=tuple(messages),
            started_at=time.time(),
            metadata=metadata or {},
        )

        with self._lock:
            self._tasks[task_id] = task

        try:
            decision, stream = await self._agent.respond(
                messages,
                task_type=task_type,
                sensitivity=sens,
            )

            tokens: list[str] = []
            async for chunk in stream:
                tokens.append(chunk)

            content = "".join(tokens)
            duration_ms = (time.monotonic() - start_time) * 1000

            finished = HermesAgentTask(
                task_id=task_id,
                agent_name=agent_name,
                task_type=task_type,
                status="completed",
                messages=task.messages,
                created_at=task.created_at,
                started_at=task.started_at,
                finished_at=time.time(),
                routing_decision=decision,
                result=content,
                metadata=task.metadata,
            )

            with self._lock:
                self._tasks[task_id] = finished

            return HermesAgentExecution(
                task_id=task_id,
                agent_name=agent_name,
                success=True,
                content=content,
                routing_decision=decision,
                duration_ms=duration_ms,
                metadata={"task_type": task_type, "sensitivity": sens},
            )

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            error_msg = f"{type(exc).__name__}: {exc}"

            failed = HermesAgentTask(
                task_id=task_id,
                agent_name=agent_name,
                task_type=task_type,
                status="failed",
                messages=task.messages,
                created_at=task.created_at,
                started_at=task.started_at,
                finished_at=time.time(),
                error=error_msg,
                metadata=task.metadata,
            )

            with self._lock:
                self._tasks[task_id] = failed

            return HermesAgentExecution(
                task_id=task_id,
                agent_name=agent_name,
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
            )

    async def execute_task_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str = "chat",
        sensitivity: str | None = None,
        agent_name: str = "prime",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Execute a task and stream the response tokens.

        Same as :meth:`execute_task` but yields content tokens as they
        arrive.

        Args:
            messages: Conversation messages.
            task_type: Type of task.
            sensitivity: Generation sensitivity override.
            agent_name: Agent to use.
            metadata: Optional execution metadata.

        Yields:
            Content tokens as they arrive from the Hermes Agent.

        Raises:
            HermesAgentNotConnectedError: If not connected.
        """
        if self._status != HermesAgentStatus.CONNECTED:
            raise HermesAgentNotConnectedError(
                "Cannot stream task: adapter is not connected."
            )

        if self._agent is None:
            raise HermesAgentTaskError(
                "No Hermes Agent instance available for streaming."
            )

        sens = sensitivity or self._config.default_sensitivity

        try:
            _, stream = await self._agent.respond(
                messages,
                task_type=task_type,
                sensitivity=sens,
            )

            async for chunk in stream:
                yield chunk

        except Exception as exc:
            raise HermesAgentTaskError(
                f"Streaming failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.

        Args:
            task_id: The task to cancel.

        Returns:
            ``True`` if the task was found and cancelled.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status != "running":
                return False
            self._tasks[task_id] = HermesAgentTask(
                task_id=task_id,
                agent_name=task.agent_name,
                task_type=task.task_type,
                status="cancelled",
                messages=task.messages,
                created_at=task.created_at,
                started_at=task.started_at,
                finished_at=time.time(),
                metadata=task.metadata,
            )
            return True

    async def pause_task(self, task_id: str) -> bool:
        """Pause a running task.

        Args:
            task_id: The task to pause.

        Returns:
            ``True`` if the task was found and paused.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "running":
                return False
            self._tasks[task_id] = HermesAgentTask(
                task_id=task_id,
                agent_name=task.agent_name,
                task_type=task.task_type,
                status="paused",
                messages=task.messages,
                created_at=task.created_at,
                started_at=task.started_at,
                metadata=task.metadata,
            )
            return True

    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task.

        Args:
            task_id: The task to resume.

        Returns:
            ``True`` if the task was found and resumed.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != "paused":
                return False
            self._tasks[task_id] = HermesAgentTask(
                task_id=task_id,
                agent_name=task.agent_name,
                task_type=task.task_type,
                status="running",
                messages=task.messages,
                created_at=task.created_at,
                started_at=task.started_at,
                metadata=task.metadata,
            )
            return True

    def get_task(self, task_id: str) -> Optional[HermesAgentTask]:
        """Retrieve a task by id.

        Args:
            task_id: Task identifier.

        Returns:
            The task, or ``None``.
        """
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, *, status: Optional[str] = None) -> list[HermesAgentTask]:
        """List all tasks, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of matching tasks.
        """
        with self._lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    # ------------------------------------------------------------------
    # Skills management
    # ------------------------------------------------------------------

    def list_skills(self) -> list[SkillDescriptor]:
        """List all registered skills from the skill orchestrator.

        Returns:
            A list of skill descriptors.
        """
        repo = self._skill_orchestrator._repository  # type: ignore[attr-defined]  # noqa: SLF001
        return repo.list_all()

    def load_skills(self, skill_ids: list[str]) -> int:
        """Load specific skills into the orchestrator.

        Args:
            skill_ids: Skill ids to load.

        Returns:
            Number of skills actually loaded.
        """
        count = 0
        for sid in skill_ids:
            skill = self._skill_orchestrator._repository.get(sid)  # type: ignore[attr-defined]  # noqa: SLF001
            if skill is not None:
                from backend.skills.orchestrator import SkillBundle

                bundle = SkillBundle(
                    id=f"_adapter_{sid}",
                    name="Adapter Load",
                    skill_ids=frozenset({sid}),
                )
                self._skill_orchestrator._repository.register_bundle(bundle)  # type: ignore[attr-defined]  # noqa: SLF001
                self._skill_orchestrator.load_bundle(bundle.id)
                count += 1
        return count

    def unload_skills(self, skill_ids: list[str]) -> int:
        """Unload specific skills from the orchestrator.

        Args:
            skill_ids: Skill ids to unload.

        Returns:
            Number of skills actually unloaded.
        """
        count = 0
        for sid in skill_ids:
            bundle_id = f"_adapter_{sid}"
            count += self._skill_orchestrator.unload_bundle(bundle_id)
        return count

    # ------------------------------------------------------------------
    # Memory synchronisation
    # ------------------------------------------------------------------

    async def sync_memory(
        self,
        *,
        scope: MemoryScope = MemoryScope.SESSION,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Synchronise memory between the Hermes OS UnifiedMemory and
        the Hermes Agent EchoAgent (if available).

        ``direction`` can be:
            * ``"to_hermes_agent"`` — push Hermes OS → EchoAgent.
            * ``"from_hermes_agent"`` — pull EchoAgent → Hermes OS.
            * ``"both"`` — bidirectional sync (default).

        Args:
            scope: Memory scope to sync.
            direction: Sync direction.

        Returns:
            A dict with ``pushed``, ``pulled``, ``errors`` counters.
        """
        result: dict[str, int] = {"pushed": 0, "pulled": 0, "errors": 0}

        if direction in ("to_hermes_agent", "both") and self._echo_agent is not None:
            try:
                entries = self._memory.search(
                    MemoryQuery(scope=scope)
                )
                for entry in entries.entries:
                    try:
                        self._echo_agent.remember(
                            type_=scope.value if isinstance(scope, Enum) else scope,
                            content=entry.content,
                            tags=list(entry.tags) if entry.tags else None,
                        )
                        result["pushed"] += 1
                    except Exception:
                        result["errors"] += 1
            except Exception:
                result["errors"] += 1

        if direction in ("from_hermes_agent", "both") and self._echo_agent is not None:
            try:
                echo_memories = self._echo_agent.list_memories(
                    type_=scope.value if isinstance(scope, Enum) else scope,
                )
                for mem in echo_memories:
                    try:
                        self._memory.store(
                            content=getattr(mem, "content", str(mem)),
                            scope=scope,
                            title=getattr(mem, "type_", ""),
                            tags=frozenset(getattr(mem, "tags", []) or []),
                        )
                        result["pulled"] += 1
                    except Exception:
                        result["errors"] += 1
            except Exception:
                result["errors"] += 1

        return result

    # ------------------------------------------------------------------
    # Subagent management
    # ------------------------------------------------------------------

    def create_subagent(self, agent_name: str, agent_type: str = "prime") -> str:
        """Register a subagent.

        Args:
            agent_name: Name for the subagent.
            agent_type: Agent class type (``"prime"``, ``"echo"``, ``"aegis"``).

        Returns:
            The agent name.

        Raises:
            HermesAgentError: If the subagent already exists.
        """
        with self._lock:
            if agent_name in self._subagents:
                raise HermesAgentError(
                    f"Subagent '{agent_name}' already exists."
                )
            self._subagents[agent_name] = agent_type
            return agent_name

    def list_subagents(self) -> dict[str, str]:
        """List registered subagents.

        Returns:
            Mapping of agent_name → agent_type.
        """
        with self._lock:
            return dict(self._subagents)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_event(self, handler: Callable) -> None:
        """Register an event handler.

        The handler receives ``(event_type: str, payload: dict)``.
        """
        with self._lock:
            self._handlers.append(handler)

    # ------------------------------------------------------------------
    # RuntimeInterface bridge
    # ------------------------------------------------------------------

    def as_runtime(self, runtime_name: str = "hermes-agent", runtime_version: str = "1.0.0") -> RuntimeInterface:
        """Return a RuntimeInterface-compatible wrapper around this
        adapter, so it can be registered in the RAL RuntimeRegistry.

        The returned object is a dynamic Protocol-compatible wrapper
        that delegates to the adapter methods. This allows the Hermes
        Agent adapter to be used wherever a :class:`RuntimeInterface`
        is expected (HOS-004 / HOS-005 pattern).
        """
        rname = runtime_name
        rversion = runtime_version
        adapter = self

        class HermesAgentRuntimeWrapper:
            name: str = rname
            version: str = rversion
            capabilities: CapabilitySet = CapabilitySet(
                frozenset({HermesCapability.CHAT.value, HermesCapability.CHAT_STREAM.value})
            )
            _sts: RuntimeStatus = RuntimeStatus.STOPPED

            @property
            def status(self) -> RuntimeStatus:
                return self._sts

            async def start(self) -> None:
                self._sts = RuntimeStatus.STARTING
                try:
                    await adapter.connect()
                    self._sts = RuntimeStatus.STARTED
                except Exception:
                    self._sts = RuntimeStatus.ERROR
                    raise

            async def stop(self) -> None:
                self._sts = RuntimeStatus.STOPPING
                await adapter.disconnect()
                self._sts = RuntimeStatus.STOPPED

            def get(self, capability_name: str) -> Optional[CapabilityInterface]:
                if capability_name in (HermesCapability.CHAT.value, "chat"):
                    return _adapter_chat_capability(adapter)
                return None

        def _adapter_chat_capability(adap: HermesAgentAdapter) -> Any:
            class ChatCap:
                name: str = "chat"

                async def chat(
                    self,
                    messages: list[dict[str, Any]],
                    *,
                    runtime_ctx: dict[str, Any] | None = None,
                ) -> ChatResponse:
                    execution = await adap.execute_task(
                        messages,
                        task_type=(runtime_ctx or {}).get("task_type", "chat"),
                        metadata=runtime_ctx,
                    )
                    return ChatResponse(
                        content=execution.content,
                        metadata={
                            "model": execution.routing_decision.model
                            if execution.routing_decision
                            else "unknown",
                            "provider": "hermes-agent",
                            "success": execution.success,
                            "duration_ms": execution.duration_ms,
                        },
                    )
            return ChatCap()

        return HermesAgentRuntimeWrapper()  # type: ignore[return-value]
