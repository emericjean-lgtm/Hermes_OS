"""§14 — read-only git operations.

Builds real throwaway repositories with the real git binary rather than
mocking subprocess: the whole risk in this module is *parsing git's
output*, and a mock would only ever return what I already assumed the
format was. Skipped entirely if git isn't on PATH.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from backend.security.aegis_engine import Verdict
from backend.tools import git_tools
from backend.tools.git_tools import (
    GitCommandError,
    NotARepositoryError,
    is_protected_branch,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


class _AllowingAegis:
    """Stands in for Aegis when the test isn't about the gate itself."""

    def evaluate(self, request):
        class _Decision:
            verdict = Verdict.ALLOW
            reason = "test"

        return _Decision()


class _RefusingAegis:
    def evaluate(self, request):
        class _Decision:
            verdict = Verdict.DENY
            reason = "outside ALLOWED_PATHS"

        return _Decision()


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, shell=False
    )


@pytest.fixture
def repo(tmp_path):
    """A real repository with one commit on a non-protected branch."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "--initial-branch=feature/x")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "premier commit")
    return path


# ── the protected-branch rule (pure, no git needed) ──────────────────
@pytest.mark.parametrize(
    "name",
    ["main", "master", "MAIN", "production", "prod",
     "refs/heads/main", "origin/main", "refs/remotes/origin/master", "remotes/origin/main"],
)
def test_protected_branches_are_recognised_however_they_are_written(name):
    """A future write path that only string-compared "main" would sail
    straight past a qualified ref — which is exactly the case §14 exists
    to prevent."""
    assert is_protected_branch(name) is True


@pytest.mark.parametrize(
    "name", ["feature/x", "emeric/dev", "fix/main-menu", "mainline", "premaster", ""]
)
def test_ordinary_branches_are_not_protected(name):
    assert is_protected_branch(name) is False


# ── the Aegis gate ───────────────────────────────────────────────────
def test_refusal_blocks_before_git_runs(repo, monkeypatch):
    """The gate must come first: a denied path should never reach the
    subprocess at all."""
    called = False

    def spy(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("git ran despite an Aegis refusal")

    monkeypatch.setattr(subprocess, "run", spy)

    with pytest.raises(PermissionError, match="ALLOWED_PATHS"):
        git_tools.status(_RefusingAegis(), str(repo))
    assert called is False


@pytest.mark.parametrize("operation", ["status", "log", "branches", "diff"])
def test_every_read_operation_is_gated(repo, operation):
    with pytest.raises(PermissionError):
        getattr(git_tools, operation)(_RefusingAegis(), str(repo))


# ── status ───────────────────────────────────────────────────────────
def test_clean_repository(repo):
    result = git_tools.status(_AllowingAegis(), str(repo))

    assert result.branch == "feature/x"
    assert result.dirty is False
    assert result.staged == () and result.modified == () and result.untracked == ()
    assert result.protected is False


def test_status_separates_staged_modified_and_untracked(repo):
    (repo / "staged.txt").write_text("a", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    (repo / "README.md").write_text("modifie\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("c", encoding="utf-8")

    result = git_tools.status(_AllowingAegis(), str(repo))

    assert result.dirty is True
    assert "staged.txt" in result.staged
    assert "README.md" in result.modified
    assert "untracked.txt" in result.untracked


def test_status_flags_a_protected_branch(repo):
    _git(repo, "checkout", "-b", "main")

    result = git_tools.status(_AllowingAegis(), str(repo))

    assert result.branch == "main"
    assert result.protected is True


def test_detached_head_is_reported_and_not_protected(repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, shell=False
    ).stdout.strip()
    _git(repo, "checkout", sha)

    result = git_tools.status(_AllowingAegis(), str(repo))

    assert result.detached is True
    assert result.protected is False


# ── log ──────────────────────────────────────────────────────────────
def test_log_returns_commits_newest_first(repo):
    (repo / "second.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "second.txt")
    _git(repo, "commit", "-m", "deuxieme commit")

    commits = git_tools.log(_AllowingAegis(), str(repo))

    assert [c.subject for c in commits] == ["deuxieme commit", "premier commit"]
    assert commits[0].author == "Test User"
    assert len(commits[0].sha) == 40


def test_log_respects_the_limit(repo):
    for i in range(4):
        (repo / f"f{i}.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", f"f{i}.txt")
        _git(repo, "commit", "-m", f"commit {i}")

    assert len(git_tools.log(_AllowingAegis(), str(repo), limit=2)) == 2


def test_subject_containing_the_field_separator_cannot_corrupt_parsing(repo):
    """A commit subject is attacker-influenced text in a shared repo."""
    (repo / "x.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "x.txt")
    _git(repo, "commit", "-m", "sujet avec | pipe et \t tab")

    commits = git_tools.log(_AllowingAegis(), str(repo), limit=1)

    assert commits[0].subject == "sujet avec | pipe et \t tab"


# ── branches ─────────────────────────────────────────────────────────
def test_branches_lists_locals_and_current(repo):
    _git(repo, "branch", "autre")

    result = git_tools.branches(_AllowingAegis(), str(repo))

    assert result.current == "feature/x"
    assert set(result.local) == {"feature/x", "autre"}


# ── diff ─────────────────────────────────────────────────────────────
def test_diff_shows_unstaged_changes(repo):
    (repo / "README.md").write_text("contenu modifie\n", encoding="utf-8")

    out = git_tools.diff(_AllowingAegis(), str(repo))

    assert "README.md" in out
    assert "contenu modifie" in out


def test_staged_diff_is_separate_from_unstaged(repo):
    (repo / "README.md").write_text("mis en index\n", encoding="utf-8")
    _git(repo, "add", "README.md")

    assert "mis en index" in git_tools.diff(_AllowingAegis(), str(repo), staged=True)
    assert git_tools.diff(_AllowingAegis(), str(repo), staged=False).strip() == ""


def test_huge_diff_is_truncated(repo):
    # Must be a *tracked* file: `git diff` ignores untracked ones, so
    # writing a new file here would produce an empty diff and the
    # truncation would never be exercised.
    (repo / "README.md").write_text("ligne\n" * 5000, encoding="utf-8")

    out = git_tools.diff(_AllowingAegis(), str(repo), max_chars=500)

    assert len(out) < 700
    assert "truncated" in out


# ── error paths ──────────────────────────────────────────────────────
def test_non_repository_directory(tmp_path):
    plain = tmp_path / "pas_un_depot"
    plain.mkdir()

    with pytest.raises(NotARepositoryError):
        git_tools.status(_AllowingAegis(), str(plain))


def test_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        git_tools.status(_AllowingAegis(), str(tmp_path / "absent"))


def test_git_failure_surfaces_git_own_stderr(repo, monkeypatch):
    class _Failed:
        returncode = 128
        stdout = ""
        stderr = "fatal: your current branch does not have any commits yet"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())

    with pytest.raises(GitCommandError, match="does not have any commits"):
        git_tools.status(_AllowingAegis(), str(repo))


def test_commands_never_use_a_shell(repo, monkeypatch):
    """shell=True with any caller-influenced value would be an injection
    surface; this asserts the invariant the module's docstring claims."""
    seen = {}
    real = subprocess.run

    def spy(args, **kwargs):
        seen["args"] = args
        seen["shell"] = kwargs.get("shell")
        return real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    git_tools.status(_AllowingAegis(), str(repo))

    assert seen["shell"] is False
    assert isinstance(seen["args"], list)  # never a single string
    assert seen["args"][0] == "git"
