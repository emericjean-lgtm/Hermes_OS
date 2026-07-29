"""KlaatCode data models (HOS-054B).

Follows the pattern established by tool_models.py and the GitHub connector.
Uses dataclasses for consistency with the rest of the Hermes tool platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class KlaatCodeAction(str, Enum):
    """Actions supported by the KlaatCode MCP adapter."""
    ANALYZE_PROJECT = "analyze_project"
    INSPECT_CODE = "inspect_code"
    GENERATE_CODE_PLAN = "generate_code_plan"
    EDIT_FILE = "edit_file"
    SEARCH_CODE = "search_code"
    RUN_DIAGNOSTICS = "run_diagnostics"
    VALIDATE_CHANGES = "validate_changes"
    HEALTH_CHECK = "health_check"


class KlaatCodeStatus(str, Enum):
    """Status of a KlaatCode operation."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class DiagnosticSeverity(str, Enum):
    """Severity levels for code diagnostics."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class KlaatCodeRequest:
    """Request to execute a KlaatCode operation.

    Fields:
        id: Unique request identifier.
        action: The operation to perform.
        parameters: Operation parameters (paths, queries, etc.).
        agent_id: Hermes agent making the request.
        mission_id: Parent mission context.
        timeout_seconds: Max execution time.
        workspace_id: Targeted workspace (isolated sandbox).
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    mission_id: str = ""
    timeout_seconds: float = 60.0
    workspace_id: str = ""


@dataclass
class KlaatCodeResponse:
    """Response from a KlaatCode operation.

    Fields:
        id: Unique response identifier.
        request_id: Matching request identifier.
        status: Outcome of the operation.
        data: Result payload (project analysis, code plan, diagnostics, etc.).
        error: Error message if status is not SUCCESS.
        duration_ms: Execution duration in milliseconds.
        timestamp: When the response was created.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str = ""
    status: KlaatCodeStatus = KlaatCodeStatus.SUCCESS
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class KlaatCodeProject:
    """Represents a code project under analysis by KlaatCode.

    Fields:
        root_path: Absolute or relative root of the project.
        language: Detected primary language.
        framework: Detected framework (if any).
        file_count: Total source files.
        dependency_count: Number of dependencies.
        git_enabled: Whether the project is under version control.
        structure: Project file tree as a nested dict.
    """
    root_path: str = ""
    language: str = ""
    framework: str = ""
    file_count: int = 0
    dependency_count: int = 0
    git_enabled: bool = False
    structure: dict[str, Any] = field(default_factory=dict)


@dataclass
class KlaatCodeDiagnostic:
    """Code diagnostic result from KlaatCode post-edit analysis.

    Fields:
        file_path: The file that was analysed.
        severity: Severity level.
        line: Line number (1-based).
        column: Column number (1-based).
        message: Human-readable diagnostic message.
        rule_id: Linter/analyser rule identifier.
        suggestion: Optional fix suggestion.
    """
    file_path: str = ""
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING
    line: int = 0
    column: int = 0
    message: str = ""
    rule_id: str = ""
    suggestion: str = ""


@dataclass
class KlaatCodeCapability:
    """Describes a single KlaatCode capability exposed via MCP.

    Fields:
        name: Capability name.
        description: Human-readable description.
        inputs: Expected input schema keys.
        outputs: Output schema keys.
        requires_git: Whether Git is required.
        requires_project: Whether a project context is required.
    """
    name: str = ""
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    requires_git: bool = False
    requires_project: bool = True
