"""§14 phase 2 — mutating git operations and their guards.

The point of this file is the *refusals*. Every test that asserts a
protected branch is refused is guarding a rule the cahier des charges
words as a prohibition ("jamais directement sur la branche principale"),
not as a preference — so a regression here is a safety regression, not a
cosmetic one.

Real throwaway repositories again, real git binary: a mocked subprocess
would happily "refuse" things while the real command would have run.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from backend.security.aegis_engine import Verdict
from backend.tools import git_tools

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


class _Aegis:
    """Configurable stand-in that records what it was asked about — the
    action_type matters as much as the verdict, since sending a PR
    through `git_operation` instead of `git_critical` would silently
    lower its protection at higher autonomy levels."""

    def __init__(self, verdict=Verdict.ALLOW, reason="test"):
        self._verdict, self._reason = verdict, reason
        self.seen: list[str] = []

    def evaluate(self, request):
        self.seen.append(request.action_type)
        outer = self

        class _Decision:
            verdict = outer._verdict
            reason = outer._reason

        return _Decision()


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, shell=False
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "--initial-branch=feature/x")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "premier commit")
    return path


def _on_protected(repo):
    _git(repo, "checkout", "-b", "main")


# ── the §14 prohibition: never write on the main branch ──────────────
def test_commit_on_protected_branch_is_refused(repo):
    _on_protected(repo)
    (repo / "README.md").write_text("modifie\n", encoding="utf-8")
    aegis = _Aegis()

    result = git_tools.commit(aegis, str(repo), "tentative sur main")

    assert result.applied is False
    assert result.verdict == "deny"
    assert "protected branch" in result.reason
    # Refused before Aegis is even asked: this is a prohibition, not a
    # permission that a higher autonomy level could unlock.
    assert aegis.seen == []


def test_refused_commit_really_did_not_commit(repo):
    """The refusal must be real, not just a returned object."""
    _on_protected(repo)
    (repo / "README.md").write_text("modifie\n", encoding="utf-8")
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, shell=False
    ).stdout

    git_tools.commit(_Aegis(), str(repo), "tentative")

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, shell=False
    ).stdout
    assert before == after


def test_push_to_protected_branch_is_refused(repo):
    aegis = _Aegis()

    result = git_tools.push(aegis, str(repo), branch="main")

    assert result.applied is False
    assert result.verdict == "deny"
    assert aegis.seen == []


def test_creating_a_protected_branch_name_is_refused(repo):
    """Introducing a branch called `main` is how the protected name
    appears in the first place — every later guard keys off it."""
    result = git_tools.create_branch(_Aegis(), str(repo), "main")

    assert result.applied is False
    assert "protected branch name" in result.reason


def test_revert_on_protected_branch_is_refused(repo):
    _on_protected(repo)

    result = git_tools.revert_commit(_Aegis(), str(repo), "HEAD")

    assert result.applied is False
    assert result.verdict == "deny"


def test_there_is_no_force_push_option():
    """A `force` parameter would put the history-rewriting case one
    keystroke from the safe one (§18: suppression Git critique)."""
    import inspect

    params = inspect.signature(git_tools.push).parameters
    assert "force" not in params
    assert not any("force" in p.lower() for p in params)


def test_no_destructive_reset_is_exposed():
    assert not hasattr(git_tools, "reset")
    assert not hasattr(git_tools, "reset_hard")


# ── the Aegis gate on ordinary operations ────────────────────────────
def test_aegis_refusal_blocks_commit(repo):
    (repo / "README.md").write_text("modifie\n", encoding="utf-8")
    aegis = _Aegis(verdict=Verdict.REQUIRE_HUMAN_VALIDATION, reason="autonomy too low")

    result = git_tools.commit(aegis, str(repo), "message")

    assert result.applied is False
    assert result.verdict == "require_human_validation"
    assert "autonomy" in result.reason
    assert aegis.seen == ["git_operation"]


def test_pull_request_is_classified_critical_not_ordinary(repo):
    """A PR is outward-facing: it publishes and notifies people. Sending
    it through git_operation would let a raised autonomy level
    auto-approve it."""
    aegis = _Aegis(verdict=Verdict.REQUIRE_HUMAN_VALIDATION, reason="mandatory")

    result = git_tools.create_pull_request(aegis, str(repo), "Titre", "Corps")

    assert result.applied is False
    assert aegis.seen == ["git_critical"]


@pytest.mark.parametrize(
    ("op", "kwargs"),
    [
        ("create_branch", {"name": "feature/y"}),
        ("commit", {"message": "m"}),
        ("push", {}),
        ("revert_commit", {"sha": "HEAD"}),
    ],
)
def test_ordinary_writes_use_git_operation(repo, op, kwargs):
    aegis = _Aegis(verdict=Verdict.DENY, reason="nope")

    getattr(git_tools, op)(aegis, str(repo), **kwargs)

    assert aegis.seen == ["git_operation"]


# ── the happy paths ──────────────────────────────────────────────────
def test_create_branch_then_commit(repo):
    aegis = _Aegis()

    created = git_tools.create_branch(aegis, str(repo), "feature/nouvelle")
    assert created.applied is True
    assert created.detail["branch"] == "feature/nouvelle"

    (repo / "nouveau.txt").write_text("contenu", encoding="utf-8")
    committed = git_tools.commit(aegis, str(repo), "ajoute nouveau.txt")

    assert committed.applied is True
    assert committed.detail["branch"] == "feature/nouvelle"
    assert "nouveau.txt" in committed.detail["files"]
    assert len(committed.detail["sha"]) == 40


def test_commit_limited_to_named_paths(repo):
    (repo / "a.txt").write_text("a", encoding="utf-8")
    (repo / "b.txt").write_text("b", encoding="utf-8")

    result = git_tools.commit(_Aegis(), str(repo), "seulement a", paths=["a.txt"])

    assert result.applied is True
    assert result.detail["files"] == ["a.txt"]
    assert "b.txt" in git_tools.status(_Aegis(), str(repo)).untracked


def test_commit_with_nothing_staged_is_reported_not_crashed(repo):
    result = git_tools.commit(_Aegis(), str(repo), "rien a faire")

    assert result.applied is False
    assert "Nothing staged" in result.reason
    assert result.verdict == "allow"  # not a refusal — simply nothing to do


def test_empty_message_is_refused(repo):
    (repo / "a.txt").write_text("a", encoding="utf-8")

    result = git_tools.commit(_Aegis(), str(repo), "   ")

    assert result.applied is False
    assert "Empty commit message" in result.reason


def test_revert_adds_a_commit_instead_of_erasing_one(repo):
    (repo / "regression.txt").write_text("casse", encoding="utf-8")
    git_tools.commit(_Aegis(), str(repo), "introduit une regression")
    before = git_tools.log(_Aegis(), str(repo))

    result = git_tools.revert_commit(_Aegis(), str(repo), "HEAD")

    after = git_tools.log(_Aegis(), str(repo))
    assert result.applied is True
    # History grew: the bad commit is still there, plus its undo. Nothing
    # was destroyed — that is the whole point of revert over reset.
    assert len(after) == len(before) + 1
    assert not (repo / "regression.txt").exists()
