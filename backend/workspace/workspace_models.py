"""Workspace & Sandbox models for HOS-045."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────

class WorkspaceStatus(str, Enum):
    CREATED = "created"
    OPEN = "open"
    LOCKED = "locked"
    ARCHIVED = "archived"
    DESTROYED = "destroyed"


class SandboxStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"


class ArtifactType(str, Enum):
    FILE = "file"
    PATCH = "patch"
    REPORT = "report"
    LOG = "log"
    DOCUMENTATION = "documentation"
    TEST_RESULT = "test_result"
    OTHER = "other"


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"


# ── Workspace ────────────────────────────────────────────────

@dataclass
class Workspace:
    """An isolated workspace for an agent."""

    workspace_id: str = field(default_factory=lambda: uuid4().hex)
    mission_id: str = ""
    agent_id: str = ""
    node_id: str = ""
    # Path
    root_path: str = ""
    work_dir: str = ""
    # Git
    git_branch: str = ""
    git_commit: str = ""
    repository: str = ""
    # State
    status: WorkspaceStatus = WorkspaceStatus.CREATED
    # Quotas
    max_disk_mb: int = 1024
    max_duration_seconds: float = 3600.0
    disk_used_mb: float = 0.0
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    opened_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Sandbox ──────────────────────────────────────────────────

@dataclass
class Sandbox:
    """An isolated execution sandbox."""

    sandbox_id: str = field(default_factory=lambda: uuid4().hex)
    workspace_id: str = ""
    agent_id: str = ""
    # Environment
    root_path: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    # Permissions
    read_only: bool = False
    network_access: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    # Storage
    temp_path: str = ""
    max_temp_mb: int = 512
    # State
    status: SandboxStatus = SandboxStatus.CREATED
    # Future: Docker, Podman, Firecracker, WSL
    backend: str = "local"
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Artifact ─────────────────────────────────────────────────

@dataclass
class Artifact:
    """A versioned file produced within a workspace."""

    artifact_id: str = field(default_factory=lambda: uuid4().hex)
    workspace_id: str = ""
    agent_id: str = ""
    # Content
    name: str = ""
    path: str = ""
    type: ArtifactType = ArtifactType.FILE
    size_bytes: int = 0
    mime_type: str = ""
    # Versioning
    version: int = 1
    previous_version_id: str = ""
    checksum: str = ""
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Git Branch ───────────────────────────────────────────────

@dataclass
class GitBranch:
    """A Git branch within a workspace."""

    branch_id: str = field(default_factory=lambda: uuid4().hex)
    workspace_id: str = ""
    name: str = ""
    base_branch: str = "main"
    # Operations
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_commit: str = ""
    commit_count: int = 0
    is_merged: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GitCommit:
    """A Git commit record."""

    commit_id: str = field(default_factory=lambda: uuid4().hex)
    workspace_id: str = ""
    branch_name: str = ""
    hash: str = ""
    message: str = ""
    author: str = ""
    files_changed: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Workspace Policy ─────────────────────────────────────────

@dataclass
class WorkspacePolicy:
    """A policy rule for workspaces."""

    policy_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    description: str = ""
    # Rule
    condition: str = ""  # e.g. "disk_used_mb > max_disk_mb * 0.9"
    action: PolicyAction = PolicyAction.DENY
    # Scope
    applies_to_all: bool = True
    workspace_ids: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    # Limits
    max_disk_mb: int = 0
    max_duration_seconds: float = 0.0
    read_only: bool = False
    network_allowed: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    # State
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
