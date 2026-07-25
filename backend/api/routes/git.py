"""Git endpoints — cahier des charges §14, read-only phase.

REST counterpart of the git_* MCP tools. All four operations observe a
repository; none mutates one. The write side (branch, commit, push, PR,
rollback) is a separate pass and belongs behind the `git_operation` /
`git_critical` categories in config/security.yaml, not here.

Error codes stay distinguishable for the same reason as /documents:
403 (Aegis refused) and 404 (no such path) and 400 (not a repository)
call for different reactions, and collapsing them into 500 would tell
the caller nothing.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import get_agent_registry
from backend.tools import git_tools
from backend.tools.git_tools import GitCommandError, NotARepositoryError

router = APIRouter()


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


class GitStatusResponse(BaseModel):
    branch: str
    detached: bool
    dirty: bool
    staged: list[str]
    modified: list[str]
    untracked: list[str]
    ahead: int
    behind: int
    # True when the checked-out branch is one §14 forbids writing to
    # directly. Surfaced on a read endpoint so a caller can decide
    # *before* attempting anything, rather than being refused later.
    protected: bool


class GitCommitResponse(BaseModel):
    sha: str
    author: str
    date: str
    subject: str


class GitBranchesResponse(BaseModel):
    current: str
    local: list[str]
    remote: list[str]


class GitDiffResponse(BaseModel):
    diff: str
    staged: bool


def _guard(call):
    """Map the module's exceptions onto HTTP status codes once, instead
    of repeating the same four except-clauses on every route."""
    try:
        return call()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotARepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitCommandError as exc:
        # 502: git ran and refused. The failure is downstream of us, and
        # its own stderr is carried through as the detail.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/git/status")
async def git_status(repo_path: str, project_id: str | None = None) -> GitStatusResponse:
    result = _guard(lambda: git_tools.status(_aegis(), repo_path, project_id=project_id))
    return GitStatusResponse(
        branch=result.branch,
        detached=result.detached,
        dirty=result.dirty,
        staged=list(result.staged),
        modified=list(result.modified),
        untracked=list(result.untracked),
        ahead=result.ahead,
        behind=result.behind,
        protected=result.protected,
    )


@router.get("/git/log")
async def git_log(
    repo_path: str, limit: int = 20, project_id: str | None = None
) -> list[GitCommitResponse]:
    commits = _guard(
        lambda: git_tools.log(_aegis(), repo_path, limit=limit, project_id=project_id)
    )
    return [
        GitCommitResponse(sha=c.sha, author=c.author, date=c.date, subject=c.subject)
        for c in commits
    ]


@router.get("/git/branches")
async def git_branches(repo_path: str, project_id: str | None = None) -> GitBranchesResponse:
    result = _guard(lambda: git_tools.branches(_aegis(), repo_path, project_id=project_id))
    return GitBranchesResponse(
        current=result.current, local=list(result.local), remote=list(result.remote)
    )


@router.get("/git/diff")
async def git_diff(
    repo_path: str, staged: bool = False, project_id: str | None = None
) -> GitDiffResponse:
    out = _guard(
        lambda: git_tools.diff(_aegis(), repo_path, staged=staged, project_id=project_id)
    )
    return GitDiffResponse(diff=out, staged=staged)
