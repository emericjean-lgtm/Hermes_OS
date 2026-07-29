"""Oh My Pi MCP adapter (HOS-055B).

Exposes Oh My Pi tools as MCP tools. Every call passes through:
    Policy → Sandbox → Execute → EventBus
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from backend.tools.tool_models import (
    ToolDefinition, ToolPermission, ToolRequest, ToolType, ToolCategory,
)
from backend.tools.tool_policy import ToolPolicy, PolicyVerdict
from backend.tools.tool_sandbox import ToolSandbox

from .ohmypi_client import OhMyPiClient
from .ohmypi_models import (
    OhMyPiAction, OhMyPiCapability, OhMyPiRequest, OhMyPiResponse, OhMyPiStatus,
)

OHMYPI_MCP_TOOLS: list[dict[str, Any]] = [
    {"name": OhMyPiAction.LSP_OPEN_FILE, "description": "Open file with LSP navigation (goto-def, references, hover)",
     "input_schema": {"file": "string"}, "permissions": [ToolPermission.READ]},
    {"name": OhMyPiAction.LSP_EDIT, "description": "Edit file with LSP-wired rename and import updates",
     "input_schema": {"file": "string", "edit": "string"}, "permissions": [ToolPermission.WRITE]},
    {"name": OhMyPiAction.AST_TRANSFORM, "description": "Structural AST transformation via tree-sitter",
     "input_schema": {"transform": "string", "file": "string"}, "permissions": [ToolPermission.WRITE]},
    {"name": OhMyPiAction.DEBUG_START, "description": "Start a debug session via DAP (lldb, dlv, debugpy)",
     "input_schema": {"program": "string"}, "permissions": [ToolPermission.READ]},
    {"name": OhMyPiAction.DEBUG_STEP, "description": "Step through debugger (step over/into/out)",
     "input_schema": {}, "permissions": [ToolPermission.READ]},
    {"name": OhMyPiAction.EXECUTE_PYTHON, "description": "Execute Python code with tool callback support",
     "input_schema": {"code": "string"}, "permissions": [ToolPermission.READ]},
    {"name": OhMyPiAction.EXECUTE_JAVASCRIPT, "description": "Execute JavaScript code with tool callback support",
     "input_schema": {"code": "string"}, "permissions": [ToolPermission.READ]},
    {"name": OhMyPiAction.GIT_OPERATION, "description": "Git operation (diff, log, branch, commit)",
     "input_schema": {"op": "string", "args": "list"}, "permissions": [ToolPermission.WRITE]},
    {"name": OhMyPiAction.CODE_SEARCH, "description": "Search code using Oh My Pi's Rust-native search",
     "input_schema": {"query": "string"}, "permissions": [ToolPermission.READ]},
]


class OhMyPiMCPAdapter:
    EVENT_PREFIX = "ohmypi"
    EVENT_EXECUTION_STARTED = f"{EVENT_PREFIX}.execution.started"
    EVENT_EXECUTION_COMPLETED = f"{EVENT_PREFIX}.execution.completed"
    EVENT_EXECUTION_FAILED = f"{EVENT_PREFIX}.execution.failed"

    def __init__(self, client: OhMyPiClient, policy: ToolPolicy,
                 sandbox: ToolSandbox, event_bus: Any = None) -> None:
        self._client = client
        self._policy = policy
        self._sandbox = sandbox
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._tool_definitions: dict[str, ToolDefinition] = {}
        self._capabilities: list[OhMyPiCapability] = []
        self._register_tools()

    def _register_tools(self) -> None:
        for spec in OHMYPI_MCP_TOOLS:
            name = spec["name"]
            td = ToolDefinition(
                name=f"ohmypi.{name}", tool_type=ToolType.CUSTOM,
                category=ToolCategory.SYSTEM, description=spec["description"],
                permissions=spec["permissions"],
                tags=["ohmypi", "lsp", "debug", "ast", "rust-native"],
                timeout_seconds=120.0, max_retries=2,
                sandbox_required=True, policy_required=True,
            )
            self._tool_definitions[name] = td
            self._capabilities.append(OhMyPiCapability(
                name=name, description=spec["description"],
                inputs=list(spec["input_schema"].keys()),
                requires_workspace=True, requires_lsp="lsp" in name,
            ))

    def get_tool_definitions(self) -> dict[str, ToolDefinition]:
        return dict(self._tool_definitions)

    def get_capabilities(self) -> list[OhMyPiCapability]:
        return list(self._capabilities)

    def execute(self, action: str, parameters: dict[str, Any],
                agent_id: str = "", mission_id: str = "") -> OhMyPiResponse:
        td = self._tool_definitions.get(action)
        if td is None:
            return OhMyPiResponse(status=OhMyPiStatus.ERROR, error=f"Unknown action: '{action}'")

        perm = ToolPermission.WRITE if action in (
            OhMyPiAction.LSP_EDIT, OhMyPiAction.AST_TRANSFORM, OhMyPiAction.GIT_OPERATION
        ) else ToolPermission.READ
        verdict, reason = self._policy.evaluate(
            ToolRequest(tool_id=td.id, action=action, parameters=parameters,
                        agent_id=agent_id, mission_id=mission_id, permission_level=perm,
                        timeout_seconds=td.timeout_seconds), td)
        if verdict == PolicyVerdict.DENY:
            return OhMyPiResponse(status=OhMyPiStatus.ERROR, error=f"Policy denied: {reason}")

        self._publish(self.EVENT_EXECUTION_STARTED, {"action": action, "agent_id": agent_id})

        response = self._client.execute(OhMyPiRequest(
            action=action, parameters=parameters, agent_id=agent_id,
            mission_id=mission_id, timeout_seconds=td.timeout_seconds))

        if response.status == OhMyPiStatus.SUCCESS:
            self._publish(self.EVENT_EXECUTION_COMPLETED, {"action": action, "duration_ms": response.duration_ms})
        else:
            self._publish(self.EVENT_EXECUTION_FAILED, {"action": action, "error": response.error}, "error")

        return response

    def get_status(self) -> dict:
        return {"installed": self._client.is_installed(), "version": self._client.get_version(),
                "tools_count": len(self._tool_definitions),
                "capabilities": [c.name for c in self._capabilities],
                "client_stats": self._client.stats()}

    def _publish(self, event_type: str, payload: dict, severity: str = "info") -> None:
        if self._event_bus is None:
            return
        try:
            from backend.runtime.events.event_models import RuntimeEventModel, RuntimeEventSeverity
            sev = RuntimeEventSeverity.ERROR if severity == "error" else RuntimeEventSeverity.INFO
            self._event_bus.publish(RuntimeEventModel(
                runtime_id="ohmypi", event_type=event_type, severity=sev,
                source="ohmypi_mcp_adapter", payload=payload))
        except Exception:
            pass
