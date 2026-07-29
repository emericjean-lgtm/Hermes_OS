"""Tool models for MCP & External Tools Platform (HOS-049)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class ToolType(str, Enum):
    MCP = "mcp"
    GITHUB = "github"
    GITLAB = "gitlab"
    DOCKER = "docker"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    REST_API = "rest_api"
    BROWSER = "browser"
    CUSTOM = "custom"


class ToolCategory(str, Enum):
    VCS = "vcs"
    CONTAINER = "container"
    DATA = "data"
    FILE = "file"
    NETWORK = "network"
    BROWSER = "browser"
    SYSTEM = "system"


class ToolStatus(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    DENIED = "denied"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class ToolDefinition:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    tool_type: ToolType = ToolType.CUSTOM
    category: ToolCategory = ToolCategory.SYSTEM
    version: str = "1.0.0"
    description: str = ""
    permissions: list[ToolPermission] = field(default_factory=lambda: [ToolPermission.READ])
    dependencies: list[str] = field(default_factory=list)
    resource_cost_mb: float = 0.0
    timeout_seconds: float = 30.0
    max_retries: int = 3
    status: ToolStatus = ToolStatus.AVAILABLE
    tags: list[str] = field(default_factory=list)
    sandbox_required: bool = True
    policy_required: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ToolInstance:
    id: str = field(default_factory=lambda: str(uuid4()))
    tool_id: str = ""
    health: HealthStatus = HealthStatus.HEALTHY
    latency_ms: float = 0.0
    error_count: int = 0
    total_executions: int = 0
    last_health_check: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ToolRequest:
    id: str = field(default_factory=lambda: str(uuid4()))
    tool_id: str = ""
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    mission_id: str = ""
    permission_level: ToolPermission = ToolPermission.READ
    timeout_seconds: float = 30.0


@dataclass
class ToolResult:
    id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str = ""
    tool_id: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    memory_used_mb: float = 0.0
    executed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ToolMetrics:
    tool_id: str = ""
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    denial_count: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    last_used: Optional[datetime] = None
