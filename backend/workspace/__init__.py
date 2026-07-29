"""Workspace & Sandbox Manager (HOS-045).

Isolated workspaces and sandboxes per agent.
Git abstraction, artifact versioning, and policy enforcement.
"""

from backend.workspace.workspace_models import (
    Workspace,
    WorkspaceStatus,
    Sandbox,
    SandboxStatus,
    Artifact,
    ArtifactType,
    GitBranch,
    GitCommit,
    WorkspacePolicy,
    PolicyAction,
)
from backend.workspace.git_workspace import GitWorkspace
from backend.workspace.sandbox_manager import SandboxManager
from backend.workspace.artifact_manager import ArtifactManager
from backend.workspace.workspace_policy import WorkspacePolicyEngine
from backend.workspace.workspace_manager import WorkspaceManager

__all__ = [
    "Workspace",
    "WorkspaceStatus",
    "Sandbox",
    "SandboxStatus",
    "Artifact",
    "ArtifactType",
    "GitBranch",
    "GitCommit",
    "WorkspacePolicy",
    "PolicyAction",
    "GitWorkspace",
    "SandboxManager",
    "ArtifactManager",
    "WorkspacePolicyEngine",
    "WorkspaceManager",
]
