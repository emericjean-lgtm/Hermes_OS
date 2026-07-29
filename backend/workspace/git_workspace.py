"""Git Workspace abstraction for HOS-045.

Provides a clean abstraction over Git operations.
Never modifies the main branch directly — always creates feature branches.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from backend.workspace.workspace_models import GitBranch, GitCommit


class GitWorkspace:
    """Abstracts Git operations for a workspace.

    All writes go through feature branches. Main branch is never modified directly.
    Thread-safe. Replaceable with other VCS later.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._branches: dict[str, list[GitBranch]] = {}  # workspace_id → branches
        self._commits: dict[str, list[GitCommit]] = {}  # workspace_id → commits

    def create_branch(
        self,
        workspace_id: str,
        name: str,
        base_branch: str = "main",
    ) -> GitBranch:
        """Create a feature branch. Never touches main directly."""
        branch = GitBranch(
            workspace_id=workspace_id,
            name=name,
            base_branch=base_branch,
        )
        with self._lock:
            self._branches.setdefault(workspace_id, []).append(branch)

        if self._on_event:
            self._on_event("git.branch_created", {
                "workspace_id": workspace_id,
                "branch": name,
                "base": base_branch,
            }, severity="info")
        return branch

    def commit(
        self,
        workspace_id: str,
        branch_name: str,
        message: str,
        author: str = "hermes-agent",
        files_changed: int = 0,
    ) -> GitCommit:
        """Record a commit on a branch."""
        import hashlib
        hash_input = f"{workspace_id}:{branch_name}:{message}:{author}"
        commit_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]

        commit = GitCommit(
            workspace_id=workspace_id,
            branch_name=branch_name,
            hash=commit_hash,
            message=message,
            author=author,
            files_changed=files_changed,
        )
        with self._lock:
            self._commits.setdefault(workspace_id, []).append(commit)
            # Update branch
            for b in self._branches.get(workspace_id, []):
                if b.name == branch_name:
                    b.last_commit = commit_hash
                    b.commit_count += 1

        if self._on_event:
            self._on_event("git.commit_created", {
                "workspace_id": workspace_id,
                "branch": branch_name,
                "hash": commit_hash,
                "message": message,
            }, severity="info")
        return commit

    def stash(self, workspace_id: str, description: str = "") -> str:
        """Simulate git stash. Returns stash reference."""
        stash_ref = f"stash@{{{len(self._commits.get(workspace_id, []))}}}"
        return stash_ref

    def merge(
        self,
        workspace_id: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> bool:
        """Merge a feature branch into target."""
        with self._lock:
            branches = self._branches.get(workspace_id, [])
            src = next((b for b in branches if b.name == source_branch), None)
            if src is None:
                return False
            src.is_merged = True
        return True

    def rollback(
        self,
        workspace_id: str,
        branch_name: str,
        commit_hash: str = "",
    ) -> bool:
        """Rollback to a previous commit on a branch."""
        return True  # always succeeds in abstraction

    def get_branches(self, workspace_id: str) -> list[GitBranch]:
        with self._lock:
            return list(self._branches.get(workspace_id, []))

    def get_commits(self, workspace_id: str, branch_name: str = "") -> list[GitCommit]:
        with self._lock:
            commits = self._commits.get(workspace_id, [])
            if branch_name:
                commits = [c for c in commits if c.branch_name == branch_name]
            return commits

    def get_branch(self, workspace_id: str, name: str) -> Optional[GitBranch]:
        with self._lock:
            for b in self._branches.get(workspace_id, []):
                if b.name == name:
                    return b
        return None

    def has_unmerged(self, workspace_id: str) -> bool:
        with self._lock:
            return any(
                not b.is_merged
                for b in self._branches.get(workspace_id, [])
            )
