"""Tests for the Workspace & Sandbox Manager (HOS-045)."""

from __future__ import annotations

import threading

import pytest

from backend.workspace.artifact_manager import ArtifactManager
from backend.workspace.git_workspace import GitWorkspace
from backend.workspace.sandbox_manager import SandboxManager
from backend.workspace.workspace_manager import WorkspaceManager
from backend.workspace.workspace_models import (
    ArtifactType,
    PolicyAction,
    SandboxStatus,
    WorkspaceStatus,
)
from backend.workspace.workspace_policy import WorkspacePolicyEngine


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def git_ws() -> GitWorkspace:
    return GitWorkspace()


@pytest.fixture
def sandbox_mgr() -> SandboxManager:
    return SandboxManager()


@pytest.fixture
def artifact_mgr() -> ArtifactManager:
    return ArtifactManager()


@pytest.fixture
def policy_engine() -> WorkspacePolicyEngine:
    return WorkspacePolicyEngine()


@pytest.fixture
def manager() -> WorkspaceManager:
    return WorkspaceManager()


# ── Git Workspace Tests ──────────────────────────────────────

class TestGitWorkspace:
    def test_create_branch(self, git_ws):
        b = git_ws.create_branch("ws1", "feature/auth")
        assert b.name == "feature/auth"
        assert b.base_branch == "main"
        assert not b.is_merged

    def test_commit(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        c = git_ws.commit("ws1", "feature/x", "Add login", files_changed=3)
        assert c.hash
        assert c.branch_name == "feature/x"
        assert c.files_changed == 3

    def test_commit_updates_branch(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        c = git_ws.commit("ws1", "feature/x", "Fix bug")
        b = git_ws.get_branch("ws1", "feature/x")
        assert b.last_commit == c.hash
        assert b.commit_count == 1

    def test_merge(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        assert git_ws.merge("ws1", "feature/x")
        b = git_ws.get_branch("ws1", "feature/x")
        assert b.is_merged

    def test_rollback(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        assert git_ws.rollback("ws1", "feature/x", "abc123")

    def test_get_branches(self, git_ws):
        git_ws.create_branch("ws1", "feature/a")
        git_ws.create_branch("ws1", "feature/b")
        branches = git_ws.get_branches("ws1")
        assert len(branches) == 2

    def test_get_commits(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        git_ws.commit("ws1", "feature/x", "Commit 1")
        git_ws.commit("ws1", "feature/x", "Commit 2")
        commits = git_ws.get_commits("ws1", "feature/x")
        assert len(commits) == 2

    def test_has_unmerged(self, git_ws):
        git_ws.create_branch("ws1", "feature/x")
        assert git_ws.has_unmerged("ws1")
        git_ws.merge("ws1", "feature/x")
        assert not git_ws.has_unmerged("ws1")

    def test_stash(self, git_ws):
        ref = git_ws.stash("ws1", "WIP")
        assert "stash" in ref


# ── Sandbox Manager Tests ────────────────────────────────────

class TestSandboxManager:
    def test_create(self, sandbox_mgr):
        sb = sandbox_mgr.create("ws1", "agent1", {"MY_VAR": "val"})
        assert sb.sandbox_id
        assert sb.agent_id == "agent1"
        assert sb.env_vars["MY_VAR"] == "val"

    def test_start_stop_destroy(self, sandbox_mgr):
        sb = sandbox_mgr.create("ws1", "agent1")
        assert sandbox_mgr.start(sb.sandbox_id)
        assert sandbox_mgr.get(sb.sandbox_id).status == SandboxStatus.RUNNING
        assert sandbox_mgr.stop(sb.sandbox_id)
        assert sandbox_mgr.get(sb.sandbox_id).status == SandboxStatus.STOPPED
        assert sandbox_mgr.destroy(sb.sandbox_id)
        assert sandbox_mgr.get(sb.sandbox_id).status == SandboxStatus.DESTROYED

    def test_get_by_workspace(self, sandbox_mgr):
        sandbox_mgr.create("ws1", "agent1")
        sandbox_mgr.create("ws1", "agent2")
        sandboxes = sandbox_mgr.get_by_workspace("ws1")
        assert len(sandboxes) == 2

    def test_get_by_agent(self, sandbox_mgr):
        sandbox_mgr.create("ws1", "agent1")
        sandbox_mgr.create("ws2", "agent1")
        sandboxes = sandbox_mgr.get_by_agent("agent1")
        assert len(sandboxes) == 2

    def test_get_active(self, sandbox_mgr):
        sb = sandbox_mgr.create("ws1", "agent1")
        sandbox_mgr.start(sb.sandbox_id)
        active = sandbox_mgr.get_active()
        assert len(active) == 1

    def test_cleanup(self, sandbox_mgr):
        sb = sandbox_mgr.create("ws1", "agent1")
        sandbox_mgr.destroy(sb.sandbox_id)
        count = sandbox_mgr.cleanup()
        assert count >= 1

    def test_stats(self, sandbox_mgr):
        sandbox_mgr.create("ws1", "agent1")
        stats = sandbox_mgr.stats()
        assert stats["total"] >= 1


# ── Artifact Manager Tests ───────────────────────────────────

class TestArtifactManager:
    def test_create(self, artifact_mgr):
        a = artifact_mgr.create("ws1", "agent1", "README.md", "/ws1/README.md",
                                ArtifactType.DOCUMENTATION, content="# Hello")
        assert a.artifact_id
        assert a.version == 1
        assert a.checksum

    def test_versioning(self, artifact_mgr):
        a1 = artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py",
                                 content="v1")
        a2 = artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py",
                                 content="v2")
        assert a2.version == 2
        assert a2.previous_version_id == a1.artifact_id

    def test_get_versions(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py", content="v1")
        artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py", content="v2")
        versions = artifact_mgr.get_versions("file.py")
        assert len(versions) == 2

    def test_get_latest(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py", content="v1")
        a2 = artifact_mgr.create("ws1", "agent1", "file.py", "/ws1/file.py", content="v2")
        latest = artifact_mgr.get_latest("file.py")
        assert latest.artifact_id == a2.artifact_id

    def test_get_by_workspace(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "a.txt", "/ws1/a.txt")
        artifact_mgr.create("ws1", "agent1", "b.txt", "/ws1/b.txt")
        artifacts = artifact_mgr.get_by_workspace("ws1")
        assert len(artifacts) == 2

    def test_get_by_agent(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "a.txt", "/ws1/a.txt")
        artifact_mgr.create("ws2", "agent1", "b.txt", "/ws2/b.txt")
        artifacts = artifact_mgr.get_by_agent("agent1")
        assert len(artifacts) == 2

    def test_get_by_type(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "readme.md", "/ws1/readme.md",
                            ArtifactType.DOCUMENTATION)
        docs = artifact_mgr.get_by_type("ws1", ArtifactType.DOCUMENTATION)
        assert len(docs) == 1

    def test_list_names(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "a.txt", "/ws1/a.txt")
        artifact_mgr.create("ws1", "agent1", "b.txt", "/ws1/b.txt")
        names = artifact_mgr.list_names("ws1")
        assert len(names) == 2

    def test_stats(self, artifact_mgr):
        artifact_mgr.create("ws1", "agent1", "f.txt", "/ws1/f.txt")
        stats = artifact_mgr.stats()
        assert stats["total_artifacts"] >= 1


# ── Policy Engine Tests ──────────────────────────────────────

class TestPolicyEngine:
    def test_defaults_registered(self, policy_engine):
        policies = policy_engine.get_all()
        assert len(policies) >= 4

    def test_check_allows_normal(self, policy_engine, manager):
        ws = manager.create("m1", "agent1")
        manager.open(ws.workspace_id)
        assert policy_engine.check(ws) == PolicyAction.ALLOW

    def test_disk_quota_warning(self, policy_engine, manager):
        ws = manager.create("m1", "agent1")
        ws.disk_used_mb = 950  # > 90% of 1024
        assert policy_engine.check(ws) == PolicyAction.WARN

    def test_disk_full_deny(self, policy_engine, manager):
        ws = manager.create("m1", "agent1")
        ws.disk_used_mb = 1024  # exactly at quota
        assert policy_engine.check(ws) == PolicyAction.DENY

    def test_register_custom(self, policy_engine):
        from backend.workspace.workspace_models import WorkspacePolicy
        policy = WorkspacePolicy(name="custom", condition="read_only", applies_to_all=True)
        policy_engine.register(policy)
        assert len(policy_engine.get_all()) >= 5

    def test_stats(self, policy_engine):
        stats = policy_engine.stats()
        assert stats["total"] >= 4


# ── Workspace Manager Tests ──────────────────────────────────

class TestWorkspaceManager:
    def test_create(self, manager):
        ws = manager.create("m1", "agent1")
        assert ws.workspace_id
        assert ws.agent_id == "agent1"
        assert ws.status == WorkspaceStatus.CREATED

    def test_open_lock_release(self, manager):
        ws = manager.create("m1", "agent1")
        assert manager.open(ws.workspace_id)
        assert manager.lock(ws.workspace_id)
        assert manager.get(ws.workspace_id).status == WorkspaceStatus.LOCKED
        assert manager.release(ws.workspace_id)
        assert manager.get(ws.workspace_id).status == WorkspaceStatus.OPEN

    def test_archive(self, manager):
        ws = manager.create("m1", "agent1")
        manager.open(ws.workspace_id)
        assert manager.archive(ws.workspace_id)
        assert manager.get(ws.workspace_id).status == WorkspaceStatus.ARCHIVED

    def test_destroy(self, manager):
        ws = manager.create("m1", "agent1")
        assert manager.destroy(ws.workspace_id)
        assert manager.get(ws.workspace_id).status == WorkspaceStatus.DESTROYED

    def test_get_by_agent(self, manager):
        manager.create("m1", "agent1")
        manager.create("m2", "agent1")
        workspaces = manager.get_by_agent("agent1")
        assert len(workspaces) == 2

    def test_get_by_mission(self, manager):
        manager.create("m1", "agent1")
        manager.create("m1", "agent2")
        workspaces = manager.get_by_mission("m1")
        assert len(workspaces) == 2

    def test_get_status(self, manager):
        ws = manager.create("m1", "agent1")
        manager.open(ws.workspace_id)
        status = manager.get_status(ws.workspace_id)
        assert status["status"] == "open"

    def test_create_sandbox(self, manager):
        ws = manager.create("m1", "agent1")
        manager.open(ws.workspace_id)
        sb = manager.create_sandbox(ws.workspace_id, "agent1")
        assert sb is not None

    def test_create_artifact(self, manager):
        ws = manager.create("m1", "agent1")
        a = manager.create_artifact(ws.workspace_id, "agent1", "file.py",
                                    "/ws/file.py", content="print('hi')")
        assert a.artifact_id
        artifacts = manager.get_artifacts(ws.workspace_id)
        assert len(artifacts) == 1

    def test_git_workflow(self, manager):
        ws = manager.create("m1", "agent1")
        # Branch
        b = manager.create_branch(ws.workspace_id, "feature/auth")
        assert b is not None
        assert manager.get(ws.workspace_id).git_branch == "feature/auth"
        # Commit
        c = manager.commit(ws.workspace_id, "feature/auth", "Add auth module", files_changed=2)
        assert c is not None
        # Merge
        assert manager.merge_branch(ws.workspace_id, "feature/auth")
        branches = manager.get_branches(ws.workspace_id)
        assert branches[0].is_merged

    def test_check_policies(self, manager):
        ws = manager.create("m1", "agent1")
        manager.open(ws.workspace_id)
        result = manager.check_policies(ws.workspace_id)
        assert result == PolicyAction.ALLOW

    def test_list_all(self, manager):
        manager.create("m1", "agent1")
        manager.create("m2", "agent2")
        all_ws = manager.list_all()
        assert len(all_ws) >= 2

    def test_stats(self, manager):
        manager.create("m1", "agent1")
        stats = manager.stats()
        assert "workspaces" in stats
        assert "sandboxes" in stats
        assert "artifacts" in stats
        assert "policies" in stats

    def test_two_agents_parallel(self, manager):
        """Two agents working on different branches, then merging."""
        # Agent 1 workspace
        ws1 = manager.create("m1", "coder", repository="repo")
        manager.open(ws1.workspace_id)
        manager.create_branch(ws1.workspace_id, "feature/backend")
        manager.commit(ws1.workspace_id, "feature/backend", "Add API", files_changed=3)
        manager.create_artifact(ws1.workspace_id, "coder", "api.py", "/ws/api.py",
                                content="class API:")

        # Agent 2 workspace
        ws2 = manager.create("m1", "reviewer", repository="repo")
        manager.open(ws2.workspace_id)
        manager.create_branch(ws2.workspace_id, "feature/review")
        manager.commit(ws2.workspace_id, "feature/review", "Reviewed API", files_changed=1)

        # Merge both
        manager.merge_branch(ws1.workspace_id, "feature/backend")
        manager.merge_branch(ws2.workspace_id, "feature/review")

        # Verify
        assert manager.get_branches(ws1.workspace_id)[0].is_merged
        assert manager.get_branches(ws2.workspace_id)[0].is_merged
        assert len(manager.get_artifacts(ws1.workspace_id)) == 1


# ── Thread Safety Tests ──────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_workspace_creation(self, manager):
        errors = []

        def worker(idx):
            try:
                manager.create("m1", f"agent{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors
        assert len(manager.list_all()) >= 20

    def test_concurrent_sandbox_creation(self, sandbox_mgr):
        errors = []

        def worker(idx):
            try:
                sandbox_mgr.create("ws1", f"agent{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors

    def test_concurrent_artifacts(self, artifact_mgr):
        errors = []

        def worker(idx):
            try:
                artifact_mgr.create("ws1", "agent1", f"file{idx}.txt",
                                    f"/ws/file{idx}.txt", content=f"v{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors
        names = artifact_mgr.list_names("ws1")
        assert len(names) >= 10
