"""Git operations — cahier des charges §14.

Phase 1: read-only. Everything here observes a repository; nothing
mutates one. Writes (branch, commit, push, PR, rollback) are deliberately
left for a second pass, behind the `git_operation` / `git_critical`
categories that config/security.yaml already declares — this module is
their first consumer, and it only needs `file_read`.

**Why this is not `system_command`.** Aegis marks `system_command` as
mandatory_validation because arbitrary shell execution is unbounded. What
happens below is not that: every command is a *constant argv list written
in this file*, run with `shell=False`, and the only caller-supplied value
is the repository path — which goes through the same ALLOWED_PATHS check
as any file read, before git is invoked at all. There is no string
interpolation into a command, so there is nothing to inject into. Gating
these reads as `system_command` would mean a human validation prompt for
`git status`, which would train the user to click through prompts — the
opposite of what the category is for.

No new dependency: the git binary is already required to use this repo,
and shelling out to it avoids adding GitPython for what amounts to four
read commands (backend/requirements.txt's "phase by phase" policy).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from backend.agents.aegis import AegisAgent
from backend.security.aegis_engine import ActionRequest, Verdict

# Branches a future write phase must never commit to or push directly
# (§14: "Jamais directement sur la branche principale"). Defined here,
# now, so the rule is testable before anything can break it.
PROTECTED_BRANCHES = frozenset({"main", "master", "production", "prod"})

# A hung git call must not hang the request thread. Read commands on a
# local repo are sub-second; 30s is pure safety margin.
_TIMEOUT_SECONDS = 30

# Unit separator — safe field delimiter for `git log --format`, since it
# cannot appear in an author name or a commit subject.
_FIELD_SEP = "\x1f"


class NotARepositoryError(ValueError):
    """The path exists and is readable, but isn't a git working tree."""


class GitCommandError(RuntimeError):
    """git ran and exited non-zero. Carries git's own stderr, which is
    almost always more useful than anything this module could invent."""


@dataclass(frozen=True)
class GitStatus:
    branch: str
    detached: bool
    dirty: bool
    staged: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    untracked: tuple[str, ...] = ()
    ahead: int = 0
    behind: int = 0
    protected: bool = False


@dataclass(frozen=True)
class GitCommit:
    sha: str
    author: str
    date: str
    subject: str


@dataclass(frozen=True)
class GitBranches:
    current: str
    local: tuple[str, ...] = field(default_factory=tuple)
    remote: tuple[str, ...] = field(default_factory=tuple)


def is_protected_branch(name: str) -> bool:
    """True for branches §14 forbids writing to directly.

    Compares the short name, so `origin/main` and `refs/heads/main` both
    resolve to protected — a future write path that only checked the raw
    string would otherwise sail straight past on a qualified ref.
    """
    short = name.strip()
    for prefix in ("refs/heads/", "refs/remotes/", "remotes/"):
        if short.startswith(prefix):
            short = short[len(prefix) :]
    if "/" in short:
        short = short.split("/", 1)[1]
    return short.lower() in PROTECTED_BRANCHES


def _check_read(aegis: AegisAgent, repo_path: str, description: str, project_id: str | None) -> None:
    decision = aegis.evaluate(
        ActionRequest(
            action_type="file_read",
            description=description,
            target_path=repo_path,
            requesting_agent="atlas",
            project_id=project_id,
        )
    )
    if decision.verdict is not Verdict.ALLOW:
        raise PermissionError(decision.reason)


def _run(repo_path: str, args: list[str]) -> str:
    """Run a fixed git argv in `repo_path` and return stdout.

    `args` is always a literal list from this module — never built from
    caller input. shell=False is the default for a list argv and is left
    explicit here so a future edit can't quietly turn this into a shell
    invocation.
    """
    target = Path(repo_path)
    if not target.exists():
        raise FileNotFoundError(f"No such path: {repo_path}")
    if not (target / ".git").exists():
        raise NotARepositoryError(f"Not a git repository: {repo_path}")

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, shell=False, path pre-checked by Aegis
            ["git", *args],
            cwd=str(target),
            capture_output=True,
            text=True,
            shell=False,
            timeout=_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:  # git itself missing
        raise GitCommandError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(f"git {' '.join(args)} timed out after {_TIMEOUT_SECONDS}s") from exc

    if completed.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(args)} failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    return completed.stdout


def status(aegis: AegisAgent, repo_path: str, *, project_id: str | None = None) -> GitStatus:
    """Branch, working-tree state, and divergence from upstream.

    Uses `--porcelain=v2`, which is the documented machine-readable
    format; the human-readable output is explicitly not a stable API and
    changes with locale.
    """
    _check_read(aegis, repo_path, f"git status in {repo_path}", project_id)
    raw = _run(repo_path, ["status", "--porcelain=v2", "--branch"])

    branch = ""
    detached = False
    ahead = behind = 0
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []

    for line in raw.splitlines():
        if line.startswith("# branch.head "):
            branch = line[len("# branch.head ") :].strip()
            detached = branch == "(detached)"
        elif line.startswith("# branch.ab "):
            # Format: "# branch.ab +2 -3"
            for token in line[len("# branch.ab ") :].split():
                if token.startswith("+"):
                    ahead = int(token[1:])
                elif token.startswith("-"):
                    behind = int(token[1:])
        elif line.startswith("? "):
            untracked.append(line[2:])
        elif line.startswith(("1 ", "2 ")):
            # "1 XY sub mH mI mW hH hI path" — XY is staged/unstaged state.
            parts = line.split(" ", 8)
            if len(parts) < 9:
                continue
            xy, path = parts[1], parts[8]
            # A rename ("2 ") stores "new\told"; the new name is what matters.
            if line.startswith("2 ") and "\t" in path:
                path = path.split("\t", 1)[0]
            if xy[0] != ".":
                staged.append(path)
            if xy[1] != ".":
                modified.append(path)

    return GitStatus(
        branch=branch,
        detached=detached,
        dirty=bool(staged or modified or untracked),
        staged=tuple(staged),
        modified=tuple(modified),
        untracked=tuple(untracked),
        ahead=ahead,
        behind=behind,
        protected=is_protected_branch(branch) if branch and not detached else False,
    )


def log(
    aegis: AegisAgent, repo_path: str, *, limit: int = 20, project_id: str | None = None
) -> list[GitCommit]:
    """Recent commits, newest first."""
    _check_read(aegis, repo_path, f"git log in {repo_path}", project_id)
    limit = max(1, min(int(limit), 500))
    fmt = _FIELD_SEP.join(["%H", "%an", "%aI", "%s"])
    raw = _run(repo_path, ["log", f"--max-count={limit}", f"--format={fmt}"])

    commits: list[GitCommit] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split(_FIELD_SEP)
        if len(fields) != 4:
            continue
        sha, author, date, subject = fields
        commits.append(GitCommit(sha=sha, author=author, date=date, subject=subject))
    return commits


def branches(aegis: AegisAgent, repo_path: str, *, project_id: str | None = None) -> GitBranches:
    """Local and remote branches, plus the current one."""
    _check_read(aegis, repo_path, f"git branch in {repo_path}", project_id)
    raw = _run(repo_path, ["branch", "--all", "--format=%(refname)"])

    local: list[str] = []
    remote: list[str] = []
    for line in raw.splitlines():
        ref = line.strip()
        if ref.startswith("refs/heads/"):
            local.append(ref[len("refs/heads/") :])
        elif ref.startswith("refs/remotes/"):
            name = ref[len("refs/remotes/") :]
            # refs/remotes/origin/HEAD is a symbolic pointer, not a branch.
            if not name.endswith("/HEAD"):
                remote.append(name)

    current = _run(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    return GitBranches(current=current, local=tuple(local), remote=tuple(remote))


def diff(
    aegis: AegisAgent,
    repo_path: str,
    *,
    staged: bool = False,
    max_chars: int = 20000,
    project_id: str | None = None,
) -> str:
    """Working-tree diff (or staged diff when `staged` is true).

    Truncated at `max_chars`: an unbounded diff can be megabytes, and
    this output usually ends up in an LLM context window.
    """
    _check_read(aegis, repo_path, f"git diff in {repo_path}", project_id)
    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    raw = _run(repo_path, args)
    if len(raw) > max_chars:
        return raw[:max_chars] + f"\n[... truncated at {max_chars} characters]"
    return raw
