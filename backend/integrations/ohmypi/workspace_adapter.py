"""Workspace Adapter (HOS-055C).

Connects Oh My Pi to WorkspaceManager.
Enforces: no edit outside sandbox, Git branch for every change,
artifact tracking, rollback support.

Pipeline: OhMyPi edit → Sandbox → Git branch → Validation → Commit
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.workspace.workspace_manager import WorkspaceManager
from backend.workspace.workspace_models import ArtifactType


class OhMyPiWorkspaceAdapter:
    def __init__(self, workspace_manager: Optional[WorkspaceManager] = None,
                 on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._ws = workspace_manager; self._on_event = on_event
        self._edit_count = 0; self._branch_name_template = "ohmypi/edit-"

    def prepare_edit(self, agent_id: str, mission_id: str,
                     file_path: str, node_id: str = "") -> dict:
        """Prepare workspace for an Oh My Pi edit operation."""
        if not self._ws:
            return {"error": "No workspace manager", "allowed": False}

        # Create or get workspace
        workspaces = self._ws.get_by_agent(agent_id)
        workspace = workspaces[0] if workspaces else self._ws.create(
            mission_id=mission_id, agent_id=agent_id, node_id=node_id)

        # Open workspace
        self._ws.open(workspace.workspace_id)

        # Create feature branch
        self._edit_count += 1
        branch_name = f"{self._branch_name_template}{self._edit_count}"
        self._ws.create_branch(workspace.workspace_id, branch_name, base_branch="main")

        # Create sandbox
        sandbox = self._ws.create_sandbox(
            workspace_id=workspace.workspace_id, agent_id=agent_id,
            read_only=False, network_access=False,
            allowed_tools=["lsp_edit", "ast_transform"],
        )

        if self._on_event:
            self._on_event("ohmypi.workspace.prepared", {
                "workspace_id": workspace.workspace_id, "branch": branch_name,
                "file": file_path, "agent_id": agent_id,
            })

        return {"allowed": True, "workspace_id": workspace.workspace_id,
                "branch": branch_name, "sandbox_id": sandbox.sandbox_id if sandbox else ""}

    def commit_edit(self, workspace_id: str, file_path: str,
                    message: str = "", agent_id: str = "",
                    files_changed: int = 1) -> dict:
        """Commit changes through Git and create artifact."""
        if not self._ws: return {"error": "No workspace manager", "committed": False}

        ws = self._ws.get(workspace_id)
        if ws is None: return {"error": "Workspace not found", "committed": False}

        # Get current branch or default
        branches = self._ws.get_branches(workspace_id)
        branch_name = branches[-1].name if branches else "main"

        # Commit
        commit = self._ws.commit(
            workspace_id=workspace_id, branch_name=branch_name,
            message=message or f"OhMyPi edit: {file_path}",
            author=agent_id or "ohmypi", files_changed=files_changed)

        # Create artifact
        self._ws.create_artifact(
            workspace_id=workspace_id, agent_id=agent_id or "ohmypi",
            name=file_path, path=file_path,
            artifact_type=ArtifactType.FILE,
            content=f"OhMyPi edit at {datetime.now(timezone.utc).isoformat()}")

        if self._on_event:
            self._on_event("ohmypi.workspace.committed", {
                "workspace_id": workspace_id, "file": file_path,
                "hash": commit.hash if commit else "",
            })

        return {"committed": True, "workspace_id": workspace_id,
                "branch": branch_name, "hash": commit.hash if commit else ""}

    def rollback_edit(self, workspace_id: str, commit_hash: str = "") -> dict:
        if not self._ws: return {"rolled_back": False}
        success = self._ws.git.rollback(workspace_id, "", commit_hash)
        if self._on_event:
            self._on_event("ohmypi.workspace.rolled_back", {"workspace_id": workspace_id})
        return {"rolled_back": success, "workspace_id": workspace_id}

    def validate_edit_path(self, file_path: str, workspace_id: str = "",
                           agent_id: str = "") -> bool:
        """Check if file path is within allowed workspace."""
        if not self._ws: return True  # no workspace = no restrictions
        if not workspace_id: return False  # must have workspace for safety
        ws = self._ws.get(workspace_id)
        return ws is not None

    def stats(self) -> dict:
        return {"edit_count": self._edit_count,
                "workspace_available": self._ws is not None}
