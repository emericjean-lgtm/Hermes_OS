"""Oh My Pi data models (HOS-055B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class OhMyPiAction(str, Enum):
    LSP_OPEN_FILE = "lsp_open_file"
    LSP_EDIT = "lsp_edit"
    AST_TRANSFORM = "ast_transform"
    DEBUG_START = "debug_start"
    DEBUG_STEP = "debug_step"
    EXECUTE_PYTHON = "execute_python"
    EXECUTE_JAVASCRIPT = "execute_javascript"
    GIT_OPERATION = "git_operation"
    CODE_SEARCH = "code_search"
    HEALTH_CHECK = "health_check"


class OhMyPiStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class OhMyPiAgentStatus(str, Enum):
    IDLE = "idle"
    EDITING = "editing"
    DEBUGGING = "debugging"
    EXECUTING = "executing"
    SEARCHING = "searching"


@dataclass
class OhMyPiRequest:
    id: str = field(default_factory=lambda: str(uuid4()))
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    mission_id: str = ""
    timeout_seconds: float = 120.0
    workspace_id: str = ""


@dataclass
class OhMyPiResponse:
    id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str = ""
    status: OhMyPiStatus = OhMyPiStatus.SUCCESS
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LSPEditResult:
    file_path: str = ""
    edits_applied: int = 0
    renames_performed: int = 0
    imports_updated: int = 0
    diagnostics_after: int = 0


@dataclass
class DebugSession:
    session_id: str = ""
    debugger_type: str = ""
    attached: bool = False
    breakpoints: list[dict] = field(default_factory=list)
    current_location: str = ""


@dataclass
class CodeExecutionResult:
    language: str = ""
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0


@dataclass
class OhMyPiCapability:
    name: str = ""
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    requires_workspace: bool = True
    requires_lsp: bool = False
