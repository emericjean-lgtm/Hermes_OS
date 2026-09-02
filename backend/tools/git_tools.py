"""Git operations — cahier des charges §14.

Reads (status/log/branches/diff) go through `file_read`. Writes (branch,
commit, push, revert, PR) go through `git_operation` or `git_critical`,
the two categories config/security.yaml has declared since the start —
this module is their first consumer.

**The safety model, in short.** At the shipped `autonomy_level: low`,
`git_operation` already resolves to require_human_validation, so nothing
mutating happens unattended by default; `git_critical` is
mandatory_validation and stays that way at *any* autonomy level. On top
of that, three things are refused outright by this module, before Aegis
is even consulted, because §14 and §18 word them as prohibitions rather
than as gated permissions:

  - committing on a protected branch (§14 "jamais directement sur la
    branche principale"),
  - pushing to a protected branch (same rule),
  - force-pushing anywhere (§18 "suppression Git critique").

A refusal is returned as a result object (applied=False + verdict +
reason), not raised — the same shape file_tools.propose_write uses, so a
caller handles a security refusal the same way whichever subsystem it
came from.

Deliberately absent: `git reset --hard` and any other history-destroying
operation. Rollback is offered as `revert_commit`, which *adds* a
commit undoing another — reversible, and it cannot lose committed work.
A destructive reset deserves its own design pass, not a flag on this one.

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


@dataclass(frozen=True)
class GitWriteResult:
    """Outcome of a mutating operation.

    Mirrors file_tools.FileWriteResult on purpose: a security refusal is
    data (applied=False + verdict + reason), not an exception, so callers
    treat "Aegis said no" identically across subsystems. `output` carries
    git's own stdout when something did run.
    """

    applied: bool
    operation: str
    verdict: str = "allow"
    reason: str = ""
    output: str = ""
    detail: dict = field(default_factory=dict)


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


def _run_gh(repo_path: str, args: list[str]) -> str:
    """Same fixed-argv discipline as _run, for the `gh` CLI.

    Separate function rather than a flag on _run: gh is a different
    binary with a different failure mode (not installed, not
    authenticated), and its "not found" message should say `gh`, not
    leave the caller hunting for a missing git.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, shell=False, path pre-checked by Aegis
            ["gh", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            shell=False,
            timeout=_TIMEOUT_SECONDS,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitCommandError(
            "gh CLI not found on PATH — required to open pull requests"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitCommandError(f"gh {' '.join(args)} timed out") from exc

    if completed.returncode != 0:
        raise GitCommandError(
            f"gh {' '.join(args)} failed ({completed.returncode}): {completed.stderr.strip()}"
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


def _check_write(
    aegis: AegisAgent,
    action_type: str,
    repo_path: str,
    description: str,
    project_id: str | None,
    discriminants: tuple[tuple[str, str], ...] = (),
) -> tuple[bool, str, str]:
    """Ask Aegis about a mutating git action.

    Returns (allowed, verdict, reason) rather than raising: callers turn
    a refusal into a GitWriteResult, matching propose_write's contract.
    `action_type` is "git_operation" or "git_critical" — never
    "file_write", because a git mutation is not confined to one path and
    the path-based whitelist would give a false sense of narrowing.

    `discriminants` porte ce qui distingue deux opérations git sur le
    **même dépôt** (HOS-224) : la branche, la cible d'un push, le sha
    d'un revert. Ces cinq appels le mettaient dans leur phrase — « Commit
    on main in C:/r » — et l'empreinte d'approbation hachait la phrase.
    Elle ne la hache plus, parce que deux autres appelants la font écrire
    par le modèle ; sans discriminant, une approbation de commit sur
    `feature/x` autoriserait donc un push sur `main`.
    """
    decision = aegis.evaluate(
        ActionRequest(
            action_type=action_type,
            description=description,
            target_path=repo_path,
            requesting_agent="atlas",
            project_id=project_id,
            discriminants=discriminants,
        )
    )
    allowed = decision.verdict is Verdict.ALLOW
    return allowed, decision.verdict.value, decision.reason


def _current_branch(repo_path: str) -> str:
    return _run(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()


def create_branch(
    aegis: AegisAgent,
    repo_path: str,
    name: str,
    *,
    from_ref: str | None = None,
    project_id: str | None = None,
) -> GitWriteResult:
    """Create a branch and check it out.

    Refuses to *create* a protected name: a branch called `main` in a repo
    that didn't have one is how a protected name gets introduced by
    accident, and every later guard keys off that name.
    """
    if is_protected_branch(name):
        return GitWriteResult(
            applied=False,
            operation="create_branch",
            verdict="deny",
            reason=f"{name!r} is a protected branch name (§14) — pick a feature branch name.",
        )

    allowed, verdict, reason = _check_write(
        aegis, "git_operation", repo_path, f"Create branch {name} in {repo_path}",
        project_id, (("op", "create_branch"), ("branch", name))
    )
    if not allowed:
        return GitWriteResult(
            applied=False, operation="create_branch", verdict=verdict, reason=reason
        )

    args = ["checkout", "-b", name]
    if from_ref:
        args.append(from_ref)
    output = _run(repo_path, args)
    return GitWriteResult(
        applied=True,
        operation="create_branch",
        output=output,
        detail={"branch": name, "from_ref": from_ref},
    )


def commit(
    aegis: AegisAgent,
    repo_path: str,
    message: str,
    *,
    paths: list[str] | None = None,
    project_id: str | None = None,
) -> GitWriteResult:
    """Stage and commit.

    `paths` limits staging to those files; omitting it stages every
    tracked modification (`git add -A`). Untracked files are included by
    -A, which is why the caller sees the file list back in `detail`.
    """
    if not message.strip():
        return GitWriteResult(
            applied=False, operation="commit", verdict="deny", reason="Empty commit message."
        )

    branch = _current_branch(repo_path)
    if is_protected_branch(branch):
        # §14, worded as a prohibition — so it is refused here rather than
        # escalated to a validation prompt a user could wave through.
        return GitWriteResult(
            applied=False,
            operation="commit",
            verdict="deny",
            reason=(
                f"Refusing to commit directly on protected branch {branch!r} "
                "(§14: jamais directement sur la branche principale). "
                "Create a feature branch first."
            ),
            detail={"branch": branch},
        )

    allowed, verdict, reason = _check_write(
        aegis, "git_operation", repo_path, f"Commit on {branch} in {repo_path}",
        project_id, (("op", "commit"), ("branch", branch))
    )
    if not allowed:
        return GitWriteResult(
            applied=False, operation="commit", verdict=verdict, reason=reason,
            detail={"branch": branch},
        )

    _run(repo_path, ["add", *(paths if paths else ["-A"])])

    staged = _run(repo_path, ["diff", "--cached", "--name-only"]).split()
    if not staged:
        return GitWriteResult(
            applied=False,
            operation="commit",
            verdict="allow",
            reason="Nothing staged — no changes to commit.",
            detail={"branch": branch},
        )

    output = _run(repo_path, ["commit", "-m", message])
    sha = _run(repo_path, ["rev-parse", "HEAD"]).strip()
    return GitWriteResult(
        applied=True,
        operation="commit",
        output=output,
        detail={"branch": branch, "sha": sha, "files": staged},
    )


def push(
    aegis: AegisAgent,
    repo_path: str,
    *,
    remote: str = "origin",
    branch: str | None = None,
    set_upstream: bool = True,
    project_id: str | None = None,
) -> GitWriteResult:
    """Push a branch to a remote.

    No force option exists on this function, by design: §18 lists
    "suppression Git critique" among the always-forbidden, and a
    force-push rewrites history other people may already have. Adding a
    `force=True` parameter would make the dangerous case one keystroke
    away from the safe one.
    """
    target = branch or _current_branch(repo_path)
    if is_protected_branch(target):
        return GitWriteResult(
            applied=False,
            operation="push",
            verdict="deny",
            reason=(
                f"Refusing to push directly to protected branch {target!r} "
                "(§14). Open a pull request instead."
            ),
            detail={"branch": target, "remote": remote},
        )

    allowed, verdict, reason = _check_write(
        aegis,
        "git_operation",
        repo_path,
        f"Push {target} to {remote} from {repo_path}",
        project_id,
        (("op", "push"), ("remote", remote), ("target", target)),
    )
    if not allowed:
        return GitWriteResult(
            applied=False, operation="push", verdict=verdict, reason=reason,
            detail={"branch": target, "remote": remote},
        )

    args = ["push"]
    if set_upstream:
        args.append("--set-upstream")
    args += [remote, target]
    output = _run(repo_path, args)
    return GitWriteResult(
        applied=True, operation="push", output=output,
        detail={"branch": target, "remote": remote},
    )


def revert_commit(
    aegis: AegisAgent,
    repo_path: str,
    sha: str,
    *,
    project_id: str | None = None,
) -> GitWriteResult:
    """Roll back a commit by *adding* one that undoes it (§14 rollback).

    `git revert`, never `git reset --hard`: revert is reversible and
    cannot lose committed work, which is the only kind of rollback safe
    to expose to an automated caller.
    """
    branch = _current_branch(repo_path)
    if is_protected_branch(branch):
        return GitWriteResult(
            applied=False,
            operation="revert_commit",
            verdict="deny",
            reason=f"Refusing to revert on protected branch {branch!r} (§14).",
            detail={"branch": branch},
        )

    allowed, verdict, reason = _check_write(
        aegis, "git_operation", repo_path, f"Revert {sha} in {repo_path}",
        project_id, (("op", "revert"), ("sha", sha))
    )
    if not allowed:
        return GitWriteResult(
            applied=False, operation="revert_commit", verdict=verdict, reason=reason
        )

    output = _run(repo_path, ["revert", "--no-edit", sha])
    new_sha = _run(repo_path, ["rev-parse", "HEAD"]).strip()
    return GitWriteResult(
        applied=True,
        operation="revert_commit",
        output=output,
        detail={"reverted": sha, "new_sha": new_sha, "branch": branch},
    )


def create_pull_request(
    aegis: AegisAgent,
    repo_path: str,
    title: str,
    body: str,
    *,
    base: str = "main",
    project_id: str | None = None,
) -> GitWriteResult:
    """Open a pull request via the `gh` CLI.

    Classified `git_critical`, i.e. mandatory_validation at every autonomy
    level — unlike a local commit, this is outward-facing: it publishes to
    a hosting service and notifies people. §18 puts that class of action
    firmly in "toujours validé par l'utilisateur".
    """
    head = _current_branch(repo_path)
    if is_protected_branch(head):
        return GitWriteResult(
            applied=False,
            operation="create_pull_request",
            verdict="deny",
            reason=f"Head branch {head!r} is protected — nothing to open a PR from (§14).",
            detail={"head": head},
        )

    allowed, verdict, reason = _check_write(
        aegis,
        "git_critical",
        repo_path,
        f"Open pull request {head} -> {base} for {repo_path}",
        project_id,
        (("op", "pull_request"), ("head", head), ("base", base)),
    )
    if not allowed:
        return GitWriteResult(
            applied=False, operation="create_pull_request", verdict=verdict, reason=reason,
            detail={"head": head, "base": base},
        )

    try:
        output = _run_gh(
            repo_path,
            ["pr", "create", "--title", title, "--body", body, "--base", base, "--head", head],
        )
    except GitCommandError as exc:
        return GitWriteResult(
            applied=False, operation="create_pull_request", verdict="allow",
            reason=str(exc), detail={"head": head, "base": base},
        )
    return GitWriteResult(
        applied=True, operation="create_pull_request", output=output,
        detail={"head": head, "base": base},
    )


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
