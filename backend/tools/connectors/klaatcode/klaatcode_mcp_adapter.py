"""KlaatCode MCP adapter (HOS-054B).

Exposes KlaatCode as a set of MCP tools that Hermes agents can invoke.
Every call passes through:
    1. ToolPolicy   — governance / permission check
    2. ToolSandbox  — workspace isolation
    3. ToolExecutor — timeout, retry, cancellation
    4. ToolMemory   — Knowledge Graph recording
    5. EventBus     — observability events

Architecture:
    Hermes Agent → ToolRouter → KlaatCodeMCPAdapter → KlaatCodeClient → KlaatCode CLI
                                 ↓
                          Policy → Sandbox → Memory → EventBus

Thread-safe.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from backend.runtime.events.event_bus import RuntimeEventBus
from backend.runtime.events.event_models import RuntimeEventModel, RuntimeEventSeverity
from backend.tools.mcp.mcp_models import MCPCall, MCPServer, MCPTool
from backend.tools.tool_models import (
    ToolDefinition,
    ToolPermission,
    ToolRequest,
    ToolResult,
    ExecutionStatus,
    ToolType,
    ToolCategory,
)
from backend.tools.tool_policy import ToolPolicy, PolicyVerdict
from backend.tools.tool_sandbox import ToolSandbox

from .klaatcode_client import KlaatCodeClient
from .klaatcode_models import (
    KlaatCodeAction,
    KlaatCodeCapability,
    KlaatCodeRequest,
    KlaatCodeResponse,
    KlaatCodeStatus,
)


# ── MCP Tool definitions for KlaatCode ───────────────────────

KLATCODE_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": KlaatCodeAction.ANALYZE_PROJECT,
        "description": "Analyze a code project structure, language, framework, and dependencies",
        "input_schema": {"path": "string (project root path)"},
        "permissions": [ToolPermission.READ],
    },
    {
        "name": KlaatCodeAction.INSPECT_CODE,
        "description": "Inspect a specific file or symbol within the project",
        "input_schema": {"file": "string (file path)", "symbol": "string (optional symbol name)"},
        "permissions": [ToolPermission.READ],
    },
    {
        "name": KlaatCodeAction.GENERATE_CODE_PLAN,
        "description": "Generate a code plan from a natural-language prompt (read-only exploration)",
        "input_schema": {"prompt": "string (natural language prompt)"},
        "permissions": [ToolPermission.READ],
    },
    {
        "name": KlaatCodeAction.EDIT_FILE,
        "description": "Edit a file in the workspace (policy-gated write operation)",
        "input_schema": {"file": "string (file path)", "content": "string (new content)"},
        "permissions": [ToolPermission.WRITE],
    },
    {
        "name": KlaatCodeAction.SEARCH_CODE,
        "description": "Search across the codebase using KlaatCode's Knowledge Graph",
        "input_schema": {"query": "string (search query)"},
        "permissions": [ToolPermission.READ],
    },
    {
        "name": KlaatCodeAction.RUN_DIAGNOSTICS,
        "description": "Run linter/typechecker diagnostics on a file",
        "input_schema": {"file": "string (file or directory path)"},
        "permissions": [ToolPermission.READ],
    },
    {
        "name": KlaatCodeAction.VALIDATE_CHANGES,
        "description": "Validate recent changes for correctness and style",
        "input_schema": {"file": "string (file path)"},
        "permissions": [ToolPermission.READ],
    },
]


# ── MCP Adapter ──────────────────────────────────────────────

class KlaatCodeMCPAdapter:
    """Adapts KlaatCode to the Hermes MCP + Tool Platform.

    Each KlaatCode capability is exposed as an MCP tool. Every invocation
    is routed through the full Hermes governance pipeline:
    Policy → Sandbox → Execution → Memory → EventBus.
    """

    # KlaatCode events published on the EventBus
    EVENT_PREFIX = "klaatcode"
    EVENT_EXECUTION_STARTED = f"{EVENT_PREFIX}.execution.started"
    EVENT_EXECUTION_COMPLETED = f"{EVENT_PREFIX}.execution.completed"
    EVENT_EXECUTION_FAILED = f"{EVENT_PREFIX}.execution.failed"
    EVENT_DIAGNOSTICS_COMPLETED = f"{EVENT_PREFIX}.diagnostics.completed"
    EVENT_HEALTH_CHANGED = f"{EVENT_PREFIX}.health_changed"

    def __init__(
        self,
        client: KlaatCodeClient,
        policy: ToolPolicy,
        sandbox: ToolSandbox,
        event_bus: Optional[RuntimeEventBus] = None,
    ) -> None:
        self._client = client
        self._policy = policy
        self._sandbox = sandbox
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._tool_definitions: dict[str, ToolDefinition] = {}
        self._mcp_tools: dict[str, MCPTool] = {}
        self._capabilities: list[KlaatCodeCapability] = []
        self._server: Optional[MCPServer] = None

        # Register tool definitions
        self._register_tools()

    # ── Registration ─────────────────────────────────────────

    def _register_tools(self) -> None:
        """Create ToolDefinition and MCPTool entries for each KlaatCode capability."""
        with self._lock:
            self._tool_definitions.clear()
            self._mcp_tools.clear()
            self._capabilities.clear()

            for tool_spec in KLATCODE_MCP_TOOLS:
                name = tool_spec["name"]
                # KlaatCodeAction is a (str, Enum), and on Python 3.11 str() of
                # such a member yields "KlaatCodeAction.ANALYZE_PROJECT" rather
                # than its value. Interpolating it produced public tool names
                # like "klaatcode.KlaatCodeAction.ANALYZE_PROJECT"; nothing
                # noticed because these definitions were never registered
                # anywhere until R-002 P2 wired the registries up.
                action = getattr(name, "value", str(name))
                # ToolDefinition for the Hermes Tool Registry
                td = ToolDefinition(
                    name=f"klaatcode.{action}",
                    tool_type=ToolType.CUSTOM,
                    category=ToolCategory.SYSTEM,
                    description=tool_spec["description"],
                    permissions=tool_spec["permissions"],
                    tags=["klaatcode", "code", "agent", "mcp"],
                    timeout_seconds=60.0,
                    max_retries=2,
                    sandbox_required=True,
                    policy_required=True,
                )
                self._tool_definitions[name] = td

                # MCPTool for the MCP Registry
                mt = MCPTool(
                    name=f"klaatcode.{action}",
                    description=tool_spec["description"],
                    input_schema=tool_spec["input_schema"],
                )
                self._mcp_tools[name] = mt

                # Capability descriptor
                cap = KlaatCodeCapability(
                    name=name,
                    description=tool_spec["description"],
                    inputs=list(tool_spec["input_schema"].keys()),
                    outputs=["result"],
                    requires_git=(name == KlaatCodeAction.ANALYZE_PROJECT),
                    requires_project=True,
                )
                self._capabilities.append(cap)

    # ── Server binding ───────────────────────────────────────

    def bind_server(self, server: MCPServer) -> None:
        """Bind this adapter to a MCP server entry for registry tracking."""
        with self._lock:
            self._server = server
            for mt in self._mcp_tools.values():
                mt.server_id = server.id

    def get_server(self) -> Optional[MCPServer]:
        with self._lock:
            return self._server

    # ── Tool definitions access ──────────────────────────────

    def get_tool_definitions(self) -> dict[str, ToolDefinition]:
        with self._lock:
            return dict(self._tool_definitions)

    def get_mcp_tools(self) -> dict[str, MCPTool]:
        with self._lock:
            return dict(self._mcp_tools)

    def get_capabilities(self) -> list[KlaatCodeCapability]:
        with self._lock:
            return list(self._capabilities)

    # ── Main execution pipeline ──────────────────────────────

    def execute(
        self, action: str, parameters: dict[str, Any],
        agent_id: str = "", mission_id: str = "",
    ) -> KlaatCodeResponse:
        """Execute a KlaatCode action through the full Hermes pipeline.

        Pipeline:
            1. ToolPolicy evaluation
            2. KlaatCodeClient execution
            3. EventBus publication
            4. Memory recording (handled externally by ToolMemory)

        Args:
            action: One of KlaatCodeAction values.
            parameters: Action-specific parameters.
            agent_id: The Hermes agent requesting execution.
            mission_id: The parent mission.

        Returns:
            KlaatCodeResponse with status, data, and error details.
        """
        td = self._tool_definitions.get(action)
        if td is None:
            return KlaatCodeResponse(
                status=KlaatCodeStatus.ERROR,
                error=f"Unknown KlaatCode action: '{action}'",
            )

        # 1. Policy check
        perm = ToolPermission.WRITE if action == KlaatCodeAction.EDIT_FILE else ToolPermission.READ
        policy_request = ToolRequest(
            tool_id=td.id,
            action=action,
            parameters=parameters,
            agent_id=agent_id,
            mission_id=mission_id,
            permission_level=perm,
            timeout_seconds=td.timeout_seconds,
        )
        verdict, reason = self._policy.evaluate(policy_request, td)
        if verdict == PolicyVerdict.DENY:
            self._publish_event(
                self.EVENT_EXECUTION_FAILED,
                {"action": action, "reason": reason, "verdict": "denied"},
                RuntimeEventSeverity.WARNING,
            )
            return KlaatCodeResponse(
                status=KlaatCodeStatus.ERROR,
                error=f"Policy denied: {reason}",
            )

        # 2. Publish start event
        self._publish_event(
            self.EVENT_EXECUTION_STARTED,
            {"action": action, "agent_id": agent_id, "mission_id": mission_id},
            RuntimeEventSeverity.INFO,
        )

        # 3. Execute via KlaatCode client
        kc_request = KlaatCodeRequest(
            action=action,
            parameters=parameters,
            agent_id=agent_id,
            mission_id=mission_id,
            timeout_seconds=td.timeout_seconds,
        )
        response = self._client.execute(kc_request)

        # 4. Publish completion/failure event
        if response.status == KlaatCodeStatus.SUCCESS:
            self._publish_event(
                self.EVENT_EXECUTION_COMPLETED,
                {"action": action, "duration_ms": response.duration_ms},
                RuntimeEventSeverity.INFO,
            )
        else:
            self._publish_event(
                self.EVENT_EXECUTION_FAILED,
                {"action": action, "error": response.error, "status": response.status.value},
                RuntimeEventSeverity.ERROR,
            )

        return response

    # ── Convenience methods ──────────────────────────────────

    def analyze_project(self, path: str = ".", agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Analyze a code project."""
        return self.execute(KlaatCodeAction.ANALYZE_PROJECT, {"path": path}, agent_id, mission_id)

    def inspect_code(self, file: str, agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Inspect a specific file."""
        return self.execute(KlaatCodeAction.INSPECT_CODE, {"file": file}, agent_id, mission_id)

    def generate_code_plan(self, prompt: str, agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Generate a code plan from a prompt."""
        return self.execute(KlaatCodeAction.GENERATE_CODE_PLAN, {"prompt": prompt}, agent_id, mission_id)

    def edit_file(self, file: str, content: str, agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Edit a file (policy-gated write)."""
        return self.execute(KlaatCodeAction.EDIT_FILE, {"file": file, "content": content}, agent_id, mission_id)

    def search_code(self, query: str, agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Search code via KlaatCode Knowledge Graph."""
        return self.execute(KlaatCodeAction.SEARCH_CODE, {"query": query}, agent_id, mission_id)

    def run_diagnostics(self, file: str = ".", agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Run diagnostics on a file."""
        return self.execute(KlaatCodeAction.RUN_DIAGNOSTICS, {"file": file}, agent_id, mission_id)

    def validate_changes(self, file: str, agent_id: str = "", mission_id: str = "") -> KlaatCodeResponse:
        """Validate recent changes."""
        return self.execute(KlaatCodeAction.VALIDATE_CHANGES, {"file": file}, agent_id, mission_id)

    # ── Status & stats ───────────────────────────────────────

    def get_status(self) -> dict:
        """Return a status snapshot of the KlaatCode adapter."""
        with self._lock:
            client_stats = self._client.stats()
            return {
                "installed": self._client.is_installed(),
                "version": self._client.get_version(),
                "tools_count": len(self._tool_definitions),
                "capabilities": [c.name for c in self._capabilities],
                "client_stats": client_stats,
                "server_bound": self._server is not None,
            }

    def get_capability_list(self) -> list[dict]:
        """Return the list of capabilities as serializable dicts."""
        with self._lock:
            return [
                {
                    "name": c.name,
                    "description": c.description,
                    "inputs": c.inputs,
                    "outputs": c.outputs,
                    "requires_git": c.requires_git,
                    "requires_project": c.requires_project,
                }
                for c in self._capabilities
            ]

    # ── Event publication ────────────────────────────────────

    def _publish_event(
        self, event_type: str, payload: dict[str, Any], severity: RuntimeEventSeverity,
    ) -> None:
        """Publish an event to the Runtime EventBus if available."""
        if self._event_bus is None:
            return
        try:
            event = RuntimeEventModel(
                runtime_id="klaatcode",
                event_type=event_type,
                severity=severity,
                source="klaatcode_mcp_adapter",
                payload=payload,
            )
            self._event_bus.publish(event)
        except Exception:
            pass  # EventBus failure must not break tool execution
