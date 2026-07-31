"""Workspace Manager — central orchestrator for HOS-045.

Coordinates workspaces, sandboxes, artifacts, Git operations, and policies.
Integrates with AgentSupervisor (HOS-043) and Mission Graph (HOS-041).
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any, Callable, Optional

from backend.workspace.artifact_manager import ArtifactManager
from backend.workspace.git_workspace import GitWorkspace
from backend.workspace.sandbox_manager import SandboxManager
from backend.workspace.workspace_models import (
    Artifact,
    ArtifactType,
    GitBranch,
    GitCommit,
    PolicyAction,
    Sandbox,
    Workspace,
    WorkspaceStatus,
)
from backend.workspace.workspace_policy import WorkspacePolicyEngine

#: Characters allowed in a directory name derived from caller-supplied ids.
#: Everything else — separators, dots, drive colons, NULs — is replaced.
_UNSAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]")


def _safe_path_component(value: str, *, fallback: str) -> str:
    """Reduce a caller-supplied id to a single, contained directory name.

    Workspace paths were built as ``f"{base}/{mission_id}/{agent_id}"``, and both
    ids come from the HTTP body. A ``mission_id`` of ``../../PWNED`` therefore
    produced a ``work_dir`` resolving to ``…/AppData/Local/PWNED/atk`` — outside
    the workspace base, which is the one thing this layer exists to guarantee.
    Nothing materialised ``work_dir`` yet, so the escape was latent rather than
    exploitable, but the containment boundary was built wrong and any future
    consumer would have inherited it.

    Sanitising rather than rejecting keeps ``create()`` total: callers already
    treat it as non-failing, and a mission id is an opaque label whose only
    requirement here is that it names exactly one directory inside the base.
    """
    if not isinstance(value, str) or not value.strip():
        return fallback
    # Take the last path segment first, so "a/b/../c" cannot contribute depth.
    leaf = PurePath(value.replace("\\", "/")).name
    cleaned = _UNSAFE_COMPONENT.sub("_", leaf).strip("._")
    # "..", "." and the empty string must never survive as a component.
    return cleaned or fallback


class WorkspaceManager:
    """Central workspace and sandbox manager.

    Coordinates:
    - Workspace lifecycle (create/open/lock/release/archive/destroy)
    - Sandbox management per agent
    - Artifact versioning
    - Git branch operations
    - Policy enforcement

    Thread-safe.
    """

    def __init__(
        self,
        base_path: str = "/tmp/hermes-workspaces",
        on_event: Optional[Callable] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._base_path = base_path
        self._on_event = on_event

        # Subsystems
        self._sandboxes = SandboxManager(
            base_path=f"{base_path}/sandboxes",
            on_event=on_event,
        )
        self._artifacts = ArtifactManager(on_event=on_event)
        self._git = GitWorkspace(on_event=on_event)
        self._policy = WorkspacePolicyEngine(on_event=on_event)

        # Storage
        self._workspaces: dict[str, Workspace] = {}
        self._by_agent: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    # ── Workspace Lifecycle ──────────────────────────────────

    def create(
        self,
        mission_id: str,
        agent_id: str,
        node_id: str = "",
        repository: str = "",
        max_disk_mb: int = 1024,
        max_duration_seconds: float = 3600.0,
    ) -> Workspace:
        """Create a new workspace for an agent.

        ``mission_id`` and ``agent_id`` are caller-supplied and reach the
        workspace path, so both are sanitised before interpolation — see
        :func:`_safe_path_component`.
        """
        ws = Workspace(
            mission_id=mission_id,
            agent_id=agent_id,
            node_id=node_id,
            root_path=self._base_path,
            work_dir=self._work_dir_for(mission_id, agent_id),
            repository=repository,
            max_disk_mb=max_disk_mb,
            max_duration_seconds=max_duration_seconds,
        )
        with self._lock:
            self._workspaces[ws.workspace_id] = ws
            self._by_agent.setdefault(agent_id, []).append(ws.workspace_id)
            self._by_mission.setdefault(mission_id, []).append(ws.workspace_id)

        if self._on_event:
            self._on_event("workspace.created", {
                "workspace_id": ws.workspace_id,
                "agent_id": agent_id,
                "mission_id": mission_id,
            }, severity="info")
        return ws

    def _work_dir_for(self, mission_id: str, agent_id: str) -> str:
        """Build the work directory, guaranteed to sit directly under the base."""
        mission = _safe_path_component(mission_id, fallback="unknown-mission")
        agent = _safe_path_component(agent_id, fallback="unknown-agent")
        return f"{self._base_path}/{mission}/{agent}"

    def open(self, workspace_id: str) -> bool:
        """Open a workspace for work."""
        return self._transition(workspace_id, WorkspaceStatus.OPEN)

    def lock(self, workspace_id: str) -> bool:
        """Lock a workspace (prevent modifications)."""
        ok = self._transition(workspace_id, WorkspaceStatus.LOCKED)
        if ok and self._on_event:
            self._on_event("workspace.locked", {
                "workspace_id": workspace_id,
            }, severity="info")
        return ok

    def release(self, workspace_id: str) -> bool:
        """Release a locked workspace."""
        ok = self._transition(workspace_id, WorkspaceStatus.OPEN)
        if ok and self._on_event:
            self._on_event("workspace.released", {
                "workspace_id": workspace_id,
            }, severity="info")
        return ok

    def archive(self, workspace_id: str) -> bool:
        """Archive a workspace."""
        ok = self._transition(workspace_id, WorkspaceStatus.ARCHIVED)
        if ok and self._on_event:
            self._on_event("workspace.archived", {
                "workspace_id": workspace_id,
            }, severity="info")
        return ok

    def destroy(self, workspace_id: str) -> bool:
        """Destroy a workspace and all its sandboxes."""
        with self._lock:
            ws = self._workspaces.get(workspace_id)
            if ws is None:
                return False
            ws.status = WorkspaceStatus.DESTROYED
            # Destroy associated sandboxes
            for sb in self._sandboxes.get_by_workspace(workspace_id):
                self._sandboxes.destroy(sb.sandbox_id)
        return True

    # ── Query ────────────────────────────────────────────────

    def get(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    def get_by_agent(self, agent_id: str) -> list[Workspace]:
        with self._lock:
            ids = self._by_agent.get(agent_id, [])
            return [self._workspaces[wid] for wid in ids if wid in self._workspaces]

    def get_by_mission(self, mission_id: str) -> list[Workspace]:
        with self._lock:
            ids = self._by_mission.get(mission_id, [])
            return [self._workspaces[wid] for wid in ids if wid in self._workspaces]

    def list_all(self) -> list[Workspace]:
        with self._lock:
            return list(self._workspaces.values())

    def get_status(self, workspace_id: str) -> dict:
        ws = self.get(workspace_id)
        if ws is None:
            return {"error": "Not found"}
        policy_check = self._policy.check(ws)
        return {
            "workspace_id": ws.workspace_id,
            "status": ws.status.value,
            "agent_id": ws.agent_id,
            "mission_id": ws.mission_id,
            "disk_used_mb": ws.disk_used_mb,
            "disk_quota_mb": ws.max_disk_mb,
            "git_branch": ws.git_branch,
            "policy_check": policy_check.value,
            "sandbox_count": len(self._sandboxes.get_by_workspace(workspace_id)),
        }

    # ── Sandbox ──────────────────────────────────────────────

    def create_sandbox(
        self,
        workspace_id: str,
        agent_id: str,
        env_vars: Optional[dict] = None,
        read_only: bool = False,
        network_access: bool = True,
        allowed_tools: Optional[list[str]] = None,
        max_temp_mb: int = 512,
    ) -> Optional[Sandbox]:
        """Create a sandbox within a workspace."""
        ws = self.get(workspace_id)
        if ws is None:
            return None

        # Apply workspace policies
        check = self._policy.check(ws)
        if check == PolicyAction.DENY:
            return None

        return self._sandboxes.create(
            workspace_id=workspace_id,
            agent_id=agent_id,
            env_vars=env_vars,
            read_only=read_only,
            network_access=network_access,
            allowed_tools=allowed_tools,
            max_temp_mb=max_temp_mb,
        )

    def get_sandboxes(self, workspace_id: str) -> list[Sandbox]:
        return self._sandboxes.get_by_workspace(workspace_id)

    # ── Artifacts ────────────────────────────────────────────

    def create_artifact(
        self,
        workspace_id: str,
        agent_id: str,
        name: str,
        path: str,
        artifact_type: ArtifactType = ArtifactType.FILE,
        content: str = "",
    ) -> Artifact:
        """Create an artifact in a workspace."""
        # Update disk usage
        ws = self.get(workspace_id)
        if ws and content:
            ws.disk_used_mb += len(content.encode()) / (1024 * 1024)
        return self._artifacts.create(
            workspace_id=workspace_id,
            agent_id=agent_id,
            name=name,
            path=path,
            artifact_type=artifact_type,
            content=content,
        )

    def get_artifacts(self, workspace_id: str) -> list[Artifact]:
        return self._artifacts.get_by_workspace(workspace_id)

    # ── Git ──────────────────────────────────────────────────

    def create_branch(
        self,
        workspace_id: str,
        name: str,
        base_branch: str = "main",
    ) -> Optional[GitBranch]:
        ws = self.get(workspace_id)
        if ws is None:
            return None
        branch = self._git.create_branch(workspace_id, name, base_branch)
        ws.git_branch = name
        return branch

    def commit(
        self,
        workspace_id: str,
        branch_name: str,
        message: str,
        author: str = "hermes-agent",
        files_changed: int = 0,
    ) -> Optional[GitCommit]:
        ws = self.get(workspace_id)
        if ws is None:
            return None
        commit = self._git.commit(workspace_id, branch_name, message, author, files_changed)
        ws.git_commit = commit.hash
        return commit

    def merge_branch(
        self,
        workspace_id: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> bool:
        return self._git.merge(workspace_id, source_branch, target_branch)

    def get_branches(self, workspace_id: str) -> list[GitBranch]:
        return self._git.get_branches(workspace_id)

    def get_commits(self, workspace_id: str, branch_name: str = "") -> list[GitCommit]:
        return self._git.get_commits(workspace_id, branch_name)

    # ── Policies ─────────────────────────────────────────────

    def check_policies(self, workspace_id: str) -> PolicyAction:
        ws = self.get(workspace_id)
        if ws is None:
            return PolicyAction.DENY
        return self._policy.check(ws)

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "workspaces": {
                    "total": len(self._workspaces),
                    "by_status": {
                        s.value: sum(1 for w in self._workspaces.values() if w.status == s)
                        for s in WorkspaceStatus
                    },
                },
                "sandboxes": self._sandboxes.stats(),
                "artifacts": self._artifacts.stats(),
                "git": {
                    "workspaces_with_branches": sum(
                        1 for wid in self._workspaces
                        if self._git.get_branches(wid)
                    ),
                },
                "policies": self._policy.stats(),
            }

    # ── Helpers ──────────────────────────────────────────────

    def _transition(self, workspace_id: str, new_status: WorkspaceStatus) -> bool:
        with self._lock:
            ws = self._workspaces.get(workspace_id)
            if ws is None:
                return False
            ws.status = new_status
            if new_status == WorkspaceStatus.OPEN and ws.opened_at is None:
                ws.opened_at = datetime.now(timezone.utc)
            elif new_status == WorkspaceStatus.LOCKED:
                ws.locked_at = datetime.now(timezone.utc)
            elif new_status == WorkspaceStatus.ARCHIVED:
                ws.archived_at = datetime.now(timezone.utc)
        return True

    # ── Properties ───────────────────────────────────────────

    @property
    def sandboxes(self) -> SandboxManager:
        return self._sandboxes

    @property
    def artifacts(self) -> ArtifactManager:
        return self._artifacts

    @property
    def git(self) -> GitWorkspace:
        return self._git

    @property
    def policy(self) -> WorkspacePolicyEngine:
        return self._policy
