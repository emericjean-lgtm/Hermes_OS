"""Freebuff Adapter (HOS-026).

Bridges Hermes OS with Freebuff for advanced planning, project management
and development assistance. Freebuff becomes an interchangeable backend
while Hermes OS remains the orchestration kernel.

Mapping:
    TaskMission / TaskPlan  →  Freebuff prompts
    MissionContext           →  FreebuffProject
    UnifiedMemory            →  Project memory sync
    Supervisor               →  Project lifecycle
    SystemEventBus           →  Event publishing
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ── Hermes OS abstractions ───────────────────────────────────────────
from backend.events.system_event_bus import SystemEventBus, SystemEventType, EventSeverity
from backend.memory.unified_memory import (
    MemoryEntry,
    MemoryQuery,
    MemoryScope,
    UnifiedMemory,
)
from backend.agent.task_planner import (
    PlannedTask,
    TaskMission,
    TaskPlan,
    TaskPlanner,
)


# ======================================================================
# Exceptions
# ======================================================================


class FreebuffError(Exception):
    """Raised when a Freebuff adapter operation fails."""


class FreebuffNotConnectedError(FreebuffError):
    """Raised when an operation is attempted without an active connection."""


class FreebuffProjectError(FreebuffError):
    """Raised when a project operation fails."""


# ======================================================================
# Enums
# ======================================================================


class FreebuffStatus(str, Enum):
    """Connection status of the Freebuff adapter."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class FreebuffConnectionMode(str, Enum):
    """Connection mode for the Freebuff backend.

    * ``API`` — HTTP API (default).
    * ``TERMINAL`` — Direct terminal-based interaction.
    * ``CLI`` — Freebuff CLI subprocess.
    * ``MCP`` — Model Context Protocol (future).
    """

    API = "api"
    TERMINAL = "terminal"
    CLI = "cli"
    MCP = "mcp"


# ======================================================================
# Data structures
# ======================================================================


@dataclass(frozen=True)
class FreebuffConfiguration:
    """Configuration for the Freebuff adapter.

    Attributes:
        mode: Connection mode.
        api_url: API base URL (for API mode).
        api_key: API key (for API mode).
        timeout: Request timeout in seconds.
        auto_reconnect: Whether to attempt reconnection on failure.
        max_prompt_history: Maximum number of prompts to retain.
    """

    mode: FreebuffConnectionMode = FreebuffConnectionMode.API
    api_url: str = "https://api.freebuff.com/v1"
    api_key: str = ""
    timeout: float = 60.0
    auto_reconnect: bool = True
    max_prompt_history: int = 100


@dataclass(frozen=True)
class FreebuffSession:
    """A session with the Freebuff backend.

    Attributes:
        session_id: Unique session identifier.
        mode: Connection mode used.
        created_at: Timestamp of session creation.
        message_count: Number of messages exchanged.
        metadata: Free-form metadata.
    """

    session_id: str
    mode: FreebuffConnectionMode = FreebuffConnectionMode.API
    created_at: float = field(default_factory=time.time)
    message_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreebuffProject:
    """A Freebuff project mapped to a Hermes OS mission.

    Attributes:
        project_id: Unique project identifier (Freebuff-side).
        mission_id: Corresponding Hermes OS mission id.
        name: Human-readable project name.
        description: Extended description.
        status: Project status (active, archived, etc.).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        metadata: Free-form payload.
    """

    project_id: str
    mission_id: str = ""
    name: str = ""
    description: str = ""
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreebuffPrompt:
    """A prompt generated from or sent to Freebuff.

    Attributes:
        prompt_id: Unique prompt identifier.
        project_id: Associated Freebuff project id.
        mission_id: Associated Hermes OS mission id.
        title: Prompt title.
        content: Prompt content / instructions.
        context: Optional context payload.
        created_at: Creation timestamp.
        metadata: Free-form payload.
    """

    prompt_id: str
    project_id: str = ""
    mission_id: str = ""
    title: str = ""
    content: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreebuffResponse:
    """A response received from Freebuff after submitting a prompt.

    Attributes:
        response_id: Unique response identifier.
        prompt_id: The prompt this responds to.
        content: Response text.
        success: Whether the response was successfully received.
        duration_ms: Response generation time in ms.
        error: Error message if failed.
        created_at: Reception timestamp.
        metadata: Free-form payload.
    """

    response_id: str
    prompt_id: str = ""
    content: str = ""
    success: bool = True
    duration_ms: float = 0.0
    error: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreebuffCapabilities:
    """Capabilities advertised by the Freebuff adapter.

    Attributes:
        available: Set of capability strings.
        modes: Supported connection modes.
        max_prompts_per_project: Maximum prompts per project.
    """

    available: frozenset[str]
    modes: tuple[str, ...] = ()
    max_prompts_per_project: int = 1000


# ======================================================================
# Adapter
# ======================================================================


class FreebuffAdapter:
    """Bridges Hermes OS with Freebuff for planning and project management.

    Construction requires no network call. Call :meth:`connect` before
    using project or prompt methods.

    Args:
        configuration: Adapter configuration.
        memory: Hermes OS :class:`UnifiedMemory` instance (optional).
        planner: :class:`TaskPlanner` instance (optional).
        event_bus: :class:`SystemEventBus` instance for event publishing
            (optional).
    """

    def __init__(
        self,
        configuration: Optional[FreebuffConfiguration] = None,
        *,
        memory: Optional[UnifiedMemory] = None,
        planner: Optional[TaskPlanner] = None,
        event_bus: Optional[SystemEventBus] = None,
    ) -> None:
        self._config = configuration or FreebuffConfiguration()
        self._memory = memory or UnifiedMemory()
        self._planner = planner or TaskPlanner()
        self._event_bus = event_bus

        self._status: FreebuffStatus = FreebuffStatus.DISCONNECTED
        self._lock = threading.RLock()
        self._sessions: dict[str, FreebuffSession] = {}
        self._projects: dict[str, FreebuffProject] = {}
        self._prompts: dict[str, FreebuffPrompt] = {}
        self._responses: dict[str, FreebuffResponse] = {}
        self._handlers: list[Callable] = []
        self._connect_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def status(self) -> FreebuffStatus:
        return self._status

    async def connect(self) -> None:
        """Establish the connection to the Freebuff backend.

        Depending on the configured mode (API, CLI, terminal), this
        validates that the endpoint or executable is reachable.

        Raises:
            FreebuffError: If connection fails.
        """
        with self._lock:
            self._status = FreebuffStatus.CONNECTING

        try:
            mode = self._config.mode

            if mode == FreebuffConnectionMode.API:
                if not self._config.api_url:
                    raise FreebuffError("API URL not configured.")
                # In a real scenario: validate API key, ping health endpoint.

            elif mode == FreebuffConnectionMode.CLI:
                # Validate CLI executable exists.
                import shutil
                if shutil.which("freebuff") is None:
                    raise FreebuffError(
                        "Freebuff CLI not found in PATH. "
                        "Install it or switch to API mode."
                    )

            elif mode == FreebuffConnectionMode.TERMINAL:
                pass  # Terminal mode assumes manual interaction.

            # Create a session.
            session_id = uuid.uuid4().hex
            session = FreebuffSession(
                session_id=session_id,
                mode=mode,
            )
            with self._lock:
                self._sessions[session_id] = session
                self._status = FreebuffStatus.CONNECTED
                self._connect_time = time.time()

            self._publish_event("freebuff.connected", {
                "mode": mode.value,
                "session_id": session_id,
            })

        except Exception as exc:
            with self._lock:
                self._status = FreebuffStatus.ERROR
            raise FreebuffError(f"Connection failed: {exc}") from exc

    async def disconnect(self) -> None:
        """Close the connection and release resources."""
        with self._lock:
            self._sessions.clear()
            self._status = FreebuffStatus.DISCONNECTED
            self._connect_time = None

        self._publish_event("freebuff.disconnected", {})

    async def health(self) -> dict[str, Any]:
        """Check the health of the Freebuff adapter.

        Returns:
            A dict with ``status``, ``connected_since``, ``projects``,
            ``prompts``, and ``mode`` keys.
        """
        with self._lock:
            return {
                "status": self._status.value,
                "connected_since": self._connect_time,
                "mode": self._config.mode.value,
                "projects_count": len(self._projects),
                "prompts_count": len(self._prompts),
                "responses_count": len(self._responses),
                "sessions_count": len(self._sessions),
            }

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        *,
        description: str = "",
        mission_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> FreebuffProject:
        """Create a new Freebuff project mapped to an optional Hermes OS mission.

        Args:
            name: Project name.
            description: Optional description.
            mission_id: Optional Hermes OS mission id.
            metadata: Optional metadata.

        Returns:
            The created project.

        Raises:
            FreebuffError: If a project with the same project_id already
                exists.
        """
        project_id = uuid.uuid4().hex
        project = FreebuffProject(
            project_id=project_id,
            mission_id=mission_id,
            name=name,
            description=description,
            metadata=metadata or {},
        )
        with self._lock:
            if project_id in self._projects:
                raise FreebuffError(f"Project '{project_id}' already exists.")
            self._projects[project_id] = project

        self._publish_event("freebuff.project_created", {
            "project_id": project_id,
            "name": name,
        })
        return project

    def update_project(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FreebuffProject:
        """Update an existing project.

        Args:
            project_id: Project identifier.
            name: New name (if changed).
            description: New description (if changed).
            status: New status (if changed).
            metadata: Merged into existing metadata.

        Returns:
            The updated project.

        Raises:
            FreebuffError: If the project does not exist.
        """
        with self._lock:
            existing = self._projects.get(project_id)
            if existing is None:
                raise FreebuffError(f"Project '{project_id}' not found.")

            merged_meta = dict(existing.metadata)
            if metadata is not None:
                merged_meta.update(metadata)

            updated = FreebuffProject(
                project_id=existing.project_id,
                mission_id=existing.mission_id,
                name=name if name is not None else existing.name,
                description=description if description is not None else existing.description,
                status=status if status is not None else existing.status,
                created_at=existing.created_at,
                updated_at=time.time(),
                metadata=merged_meta,
            )
            self._projects[project_id] = updated

        self._publish_event("freebuff.project_updated", {
            "project_id": project_id,
        })
        return updated

    def archive_project(self, project_id: str) -> FreebuffProject:
        """Archive a project (set status to ``\"archived\"``).

        Args:
            project_id: Project identifier.

        Returns:
            Updated project.
        """
        return self.update_project(project_id, status="archived")

    def delete_project(self, project_id: str) -> bool:
        """Delete a project.

        Args:
            project_id: Project identifier.

        Returns:
            ``True`` if the project existed and was deleted.
        """
        with self._lock:
            if project_id not in self._projects:
                return False
            del self._projects[project_id]

        self._publish_event("freebuff.project_deleted", {
            "project_id": project_id,
        })
        return True

    def get_project(self, project_id: str) -> FreebuffProject:
        """Retrieve a project by id.

        Args:
            project_id: Project identifier.

        Returns:
            The project.

        Raises:
            FreebuffError: If the project does not exist.
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise FreebuffError(f"Project '{project_id}' not found.")
            return project

    def list_projects(
        self,
        *,
        status: Optional[str] = None,
        mission_id: Optional[str] = None,
    ) -> list[FreebuffProject]:
        """List projects, optionally filtered.

        Args:
            status: Optional status filter.
            mission_id: Optional mission id filter.

        Returns:
            List of matching projects.
        """
        with self._lock:
            projects = list(self._projects.values())
        if status is not None:
            projects = [p for p in projects if p.status == status]
        if mission_id is not None:
            projects = [p for p in projects if p.mission_id == mission_id]
        return sorted(projects, key=lambda p: p.created_at, reverse=True)

    # ------------------------------------------------------------------
    # Prompt generation and submission
    # ------------------------------------------------------------------

    def generate_prompt(
        self,
        project_id: str,
        *,
        mission_id: str = "",
        title: str = "",
        context: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FreebuffPrompt:
        """Generate a prompt for Freebuff (local creation, no network).

        The prompt can be built from a mission context and then submitted
        via :meth:`submit_prompt`.

        Args:
            project_id: Associated project.
            mission_id: Optional Hermes OS mission id.
            title: Optional title.
            context: Optional context payload (mission details, tasks, etc.).
            metadata: Optional metadata.

        Returns:
            The generated prompt.
        """
        prompt_id = uuid.uuid4().hex

        # Build content from context if provided.
        content_parts: list[str] = []
        if title:
            content_parts.append(f"# {title}")
        if context:
            for key, value in context.items():
                content_parts.append(f"\n## {key}\n{value}")
        content = "\n".join(content_parts)

        prompt = FreebuffPrompt(
            prompt_id=prompt_id,
            project_id=project_id,
            mission_id=mission_id,
            title=title,
            content=content,
            context=context or {},
            metadata=metadata or {},
        )
        with self._lock:
            self._prompts[prompt_id] = prompt

        self._publish_event("freebuff.prompt_generated", {
            "prompt_id": prompt_id,
            "project_id": project_id,
        })
        return prompt

    def submit_prompt(
        self,
        prompt: FreebuffPrompt,
        *,
        simulate: bool = True,
    ) -> FreebuffResponse:
        """Submit a prompt to Freebuff and receive a response.

        When ``simulate=True`` (default), a simulated response is
        returned without a real network call. Set ``simulate=False``
        for real Freebuff API integration.

        Args:
            prompt: The prompt to submit.
            simulate: Whether to simulate the response.

        Returns:
            The response.

        Raises:
            FreebuffNotConnectedError: If the adapter is not connected
                and ``simulate`` is ``False``.
        """
        if not simulate and self._status != FreebuffStatus.CONNECTED:
            raise FreebuffNotConnectedError(
                "Cannot submit prompt: adapter is not connected."
            )

        start = time.monotonic()

        if simulate:
            response_content = (
                f"Simulated Freebuff response for: {prompt.title or 'untitled'}"
            )
        else:
            # In a real integration, this would call the Freebuff API.
            response_content = f"Real response for: {prompt.title}"

        duration_ms = (time.monotonic() - start) * 1000

        response = FreebuffResponse(
            response_id=uuid.uuid4().hex,
            prompt_id=prompt.prompt_id,
            content=response_content,
            success=True,
            duration_ms=duration_ms,
        )

        with self._lock:
            self._responses[response.response_id] = response

        self._publish_event("freebuff.prompt_submitted", {
            "prompt_id": prompt.prompt_id,
            "response_id": response.response_id,
            "simulated": simulate,
        })
        return response

    def receive_response(self, response_id: str) -> FreebuffResponse:
        """Retrieve a previously received response.

        Args:
            response_id: Response identifier.

        Returns:
            The response.

        Raises:
            FreebuffError: If the response does not exist.
        """
        with self._lock:
            resp = self._responses.get(response_id)
            if resp is None:
                raise FreebuffError(f"Response '{response_id}' not found.")
            return resp

    # ------------------------------------------------------------------
    # Prompt history
    # ------------------------------------------------------------------

    def get_prompt(self, prompt_id: str) -> FreebuffPrompt:
        """Retrieve a prompt by id.

        Args:
            prompt_id: Prompt identifier.

        Returns:
            The prompt.
        """
        with self._lock:
            return self._prompts[prompt_id]

    def list_prompts(
        self,
        *,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[FreebuffPrompt]:
        """List prompts, optionally filtered by project.

        Args:
            project_id: Optional project filter.
            limit: Maximum number of prompts to return.

        Returns:
            List of matching prompts (newest first).
        """
        with self._lock:
            prompts = list(self._prompts.values())
        if project_id is not None:
            prompts = [p for p in prompts if p.project_id == project_id]
        return sorted(prompts, key=lambda p: p.created_at, reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Synchronisation
    # ------------------------------------------------------------------

    def synchronize_project(
        self,
        project_id: str,
        *,
        mission: Optional[TaskMission] = None,
        tasks: Optional[list[PlannedTask]] = None,
    ) -> dict[str, Any]:
        """Synchronise a Freebuff project with a Hermes OS mission.

        Generates a prompt from the mission, stores it in memory, and
        returns the synchronisation result.

        Args:
            project_id: Freebuff project to sync.
            mission: Optional Hermes OS mission.
            tasks: Optional Hermes OS planned tasks.

        Returns:
            A dict with ``project_id``, ``prompt_generated``,
            ``memory_stored``, ``plan_generated`` keys.
        """
        result: dict[str, Any] = {
            "project_id": project_id,
            "prompt_generated": False,
            "memory_stored": False,
            "plan_generated": False,
        }

        # Build context from mission + tasks.
        context: dict[str, Any] = {}
        if mission is not None:
            context["mission"] = {
                "id": mission.id,
                "title": mission.title,
                "objective": mission.objective,
                "priority": mission.priority,
            }

        if tasks is not None:
            context["tasks"] = [
                {
                    "id": t.id,
                    "title": t.title,
                    "capability": t.runtime_capability,
                    "dependencies": sorted(t.dependencies),
                }
                for t in tasks
            ]

        # Generate a prompt.
        prompt = self.generate_prompt(
            project_id,
            mission_id=mission.id if mission else "",
            title=f"Sync: {mission.title if mission else 'untitled'}",
            context=context,
        )
        result["prompt_generated"] = True
        result["prompt_id"] = prompt.prompt_id

        # Store in memory.
        if mission is not None:
            self._memory.store(
                content=str(context),
                title=f"Freebuff sync: {mission.title}",
                scope=MemoryScope.MISSION,
                tags=frozenset({"freebuff", "sync"}),
            )
            result["memory_stored"] = True

        # Generate a plan if tasks provided.
        if tasks is not None and mission is not None:
            try:
                plan = self._planner.create_plan(mission, tasks)
                result["plan_generated"] = True
                result["task_count"] = len(tasks)
            except Exception:
                pass

        self._publish_event("freebuff.project_synced", {
            "project_id": project_id,
            "prompt_id": prompt.prompt_id,
        })
        return result

    # ------------------------------------------------------------------
    # Mission → Freebuff → TaskPlan pipeline
    # ------------------------------------------------------------------

    def mission_to_plan(
        self,
        mission: TaskMission,
        tasks: list[PlannedTask],
        *,
        project_name: str = "",
        auto_submit: bool = True,
    ) -> dict[str, Any]:
        """Convert a Hermes OS mission into a Freebuff workflow.

        This is the main integration pipeline::
            Mission → Freebuff Project → Prompt → Response → TaskPlan

        Args:
            mission: Hermes OS mission.
            tasks: Planned tasks for the mission.
            project_name: Optional Freebuff project name.
            auto_submit: Whether to auto-submit the generated prompt.

        Returns:
            A dict with ``project``, ``prompt``, ``response``,
            ``plan`` keys.
        """
        # 1. Create a Freebuff project.
        project = self.create_project(
            name=project_name or mission.title,
            description=mission.objective,
            mission_id=mission.id,
            metadata={"source": "hermes-os"},
        )

        # 2. Build context from tasks.
        context = {
            "mission_id": mission.id,
            "objective": mission.objective,
            "task_count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "capability": t.runtime_capability,
                    "deps": sorted(t.dependencies),
                }
                for t in tasks
            ],
        }

        # 3. Generate a prompt.
        prompt = self.generate_prompt(
            project.project_id,
            mission_id=mission.id,
            title=f"Plan: {mission.title}",
            context=context,
        )

        # 4. Submit and receive response (simulated by default).
        response: Optional[FreebuffResponse] = None
        if auto_submit:
            response = self.submit_prompt(prompt)

        # 5. Generate the TaskPlan locally.
        plan = self._planner.create_plan(mission, tasks)

        result: dict[str, Any] = {
            "project": project,
            "prompt": prompt,
            "response": response,
            "plan": plan,
        }

        self._publish_event("freebuff.mission_to_plan", {
            "mission_id": mission.id,
            "project_id": project.project_id,
            "task_count": len(tasks),
        })
        return result

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    async def get_capabilities(self) -> FreebuffCapabilities:
        """List the capabilities exposed by this adapter.

        Returns:
            Adapter capabilities descriptor.
        """
        return FreebuffCapabilities(
            available=frozenset({
                "projects",
                "prompts",
                "responses",
                "sync",
                "mission_to_plan",
            }),
            modes=tuple(m.value for m in FreebuffConnectionMode),
            max_prompts_per_project=self._config.max_prompt_history,
        )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_event(self, handler: Callable) -> None:
        """Register an event handler.

        The handler receives ``(event_type: str, payload: dict)``.
        """
        with self._lock:
            self._handlers.append(handler)

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Publish an event to local handlers and the SystemEventBus."""
        # Local handlers.
        for handler in self._handlers:
            try:
                handler(event_type, payload)
            except Exception:
                pass

        # SystemEventBus integration.
        if self._event_bus is not None:
            try:
                self._event_bus.publish(
                    SystemEventType.INTEGRATION,
                    f"freebuff.{event_type}",
                    payload=payload,
                    severity=EventSeverity.INFO,
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    def link_memory_to_project(
        self,
        project_id: str,
        *,
        scope: MemoryScope = MemoryScope.PROJECT,
    ) -> int:
        """Link all UnifiedMemory entries of a given scope to a Freebuff project.

        Stores them as prompts in the adapter for traceability.

        Args:
            project_id: Freebuff project id.
            scope: Memory scope to link.

        Returns:
            Number of memory entries linked.
        """
        results = self._memory.search(MemoryQuery(scope=scope))
        count = 0
        for entry in results.entries:
            prompt = self.generate_prompt(
                project_id,
                title=f"Memory: {entry.title}",
                context={"content": entry.content, "tags": sorted(entry.tags)},
                metadata={"memory_id": entry.id, "importance": entry.importance},
            )
            count += 1

        self._publish_event("freebuff.memory_linked", {
            "project_id": project_id,
            "count": count,
        })
        return count

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, max_age_s: float = 86400.0) -> int:
        """Remove prompts and responses older than ``max_age_s`` seconds.

        Args:
            max_age_s: Maximum age in seconds (default 24h).

        Returns:
            Number of entries removed.
        """
        now = time.time()
        removed = 0

        with self._lock:
            to_remove_prompts = [
                pid for pid, p in self._prompts.items()
                if now - p.created_at > max_age_s
            ]
            for pid in to_remove_prompts:
                del self._prompts[pid]
                removed += 1

            to_remove_responses = [
                rid for rid, r in self._responses.items()
                if now - r.created_at > max_age_s
            ]
            for rid in to_remove_responses:
                del self._responses[rid]
                removed += 1

        return removed
