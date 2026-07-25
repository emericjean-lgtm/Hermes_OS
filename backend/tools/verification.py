"""Verification runners — cahier des charges §16 (lint / build / tests).

This is the most dangerous module in the project, so its constraints are
worth stating plainly.

**What it does not do.** It does not execute commands. A caller names a
runner defined in config/verification.yaml and can pass nothing else — no
command, no arguments, no flags, no environment. There is no code path
here that turns caller input into an executable token, which is what
separates this from an arbitrary-shell tool.

**What it nonetheless does.** Running `pytest` in a directory executes
that directory's conftest.py and test bodies; running a build executes
its build scripts. So while the *command* is fixed, the *code that runs*
belongs to the target project. That is real execution, and it is why the
`verification_run` category (config/security.yaml) is mutating,
path-based, and — at the shipped autonomy_level of "low" — requires human
validation on every call.

Three further limits, each because the alternative bites in practice:

  - **Timeout.** A hung test suite must not hold a request thread
    forever; the process is killed and reported as timed out.
  - **Output truncation.** A failing suite can emit megabytes, and this
    output usually lands in an LLM context window.
  - **No shell.** Fixed argv, shell=False, same discipline as git_tools.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.security.aegis_engine import ActionRequest, Verdict

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "verification.yaml"

# Generous enough for a real suite, bounded enough that a runaway can't
# pin a worker indefinitely.
DEFAULT_TIMEOUT_SECONDS = 600

# Kept well under a context window; failures usually show what matters in
# the tail, so truncation keeps the head *and* the tail (see _truncate).
MAX_OUTPUT_CHARS = 20000


class UnknownRunnerError(ValueError):
    """The requested runner is not in the whitelist."""


@dataclass(frozen=True)
class Runner:
    name: str
    kind: str
    argv: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class VerificationResult:
    ran: bool
    runner: str
    kind: str = ""
    # None when the process never completed (refused, missing tool, or
    # timed out) — distinct from 0, which means it ran and passed.
    exit_code: int | None = None
    passed: bool = False
    output: str = ""
    verdict: str = "allow"
    reason: str = ""
    timed_out: bool = False
    duration_seconds: float = 0.0
    detail: dict = field(default_factory=dict)


def _load_runners() -> dict[str, Runner]:
    if not _CONFIG_PATH.exists():
        return {}
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    runners: dict[str, Runner] = {}
    for name, spec in (raw.get("runners") or {}).items():
        argv = tuple(spec.get("argv") or ())
        if not argv:
            continue
        runners[name] = Runner(
            name=name,
            kind=spec.get("kind", "unknown"),
            argv=argv,
            description=spec.get("description", ""),
        )
    return runners


def list_runners() -> list[Runner]:
    """Every runner a caller may name. Deliberately the only way to
    discover what can be executed — there is no free-form alternative."""
    return sorted(_load_runners().values(), key=lambda r: (r.kind, r.name))


def _resolve_argv(runner: Runner) -> list[str]:
    """Substitute {python} with the running interpreter.

    Uses sys.executable rather than the string "python" so a runner uses
    this backend's virtualenv instead of whatever happens to be first on
    PATH — which on Windows is frequently a different interpreter, or a
    Store stub that exits non-zero.
    """
    return [sys.executable if token == "{python}" else token for token in runner.argv]


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    # Keep both ends: a test run's useful information is split between the
    # first failure and the summary line at the very bottom. Dropping the
    # tail (the naive truncation) throws away the count of what failed.
    head = text[: int(limit * 0.6)]
    tail = text[-int(limit * 0.3) :]
    return f"{head}\n[... {len(text) - len(head) - len(tail)} characters truncated ...]\n{tail}"


def run(
    aegis: AegisAgent,
    repo_path: str,
    runner_name: str,
    *,
    timeout: int | None = None,
    project_id: str | None = None,
) -> VerificationResult:
    """Run one whitelisted verification runner in `repo_path`.

    Returns a result object on refusal (ran=False + verdict + reason)
    rather than raising, matching file_tools.propose_write and git_tools —
    a security refusal is data the caller must show the user, not an
    exception to swallow.
    """
    runners = _load_runners()
    runner = runners.get(runner_name)
    if runner is None:
        raise UnknownRunnerError(
            f"Unknown runner {runner_name!r}. Available: {', '.join(sorted(runners)) or '(none)'}"
        )

    target = Path(repo_path)
    if not target.exists():
        raise FileNotFoundError(f"No such path: {repo_path}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {repo_path}")

    decision = aegis.evaluate(
        ActionRequest(
            action_type="verification_run",
            description=f"Run {runner_name} ({runner.kind}) in {repo_path}",
            target_path=repo_path,
            requesting_agent="veritas",
            project_id=project_id,
        )
    )
    if decision.verdict is not Verdict.ALLOW:
        return VerificationResult(
            ran=False,
            runner=runner_name,
            kind=runner.kind,
            verdict=decision.verdict.value,
            reason=decision.reason,
            detail={"repo_path": repo_path},
        )

    argv = _resolve_argv(runner)
    limit = timeout or DEFAULT_TIMEOUT_SECONDS
    import time

    started = time.monotonic()
    try:
        completed = subprocess.run(  # noqa: S603 - argv from a reviewed whitelist, shell=False, path gated by Aegis
            argv,
            cwd=str(target),
            capture_output=True,
            text=True,
            shell=False,
            timeout=limit,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return VerificationResult(
            ran=False,
            runner=runner_name,
            kind=runner.kind,
            reason=f"{argv[0]!r} not found — is the tool installed for this project?",
            duration_seconds=round(time.monotonic() - started, 2),
            detail={"argv": argv},
        )
    except subprocess.TimeoutExpired:
        return VerificationResult(
            ran=False,
            runner=runner_name,
            kind=runner.kind,
            timed_out=True,
            reason=f"{runner_name} exceeded {limit}s and was terminated.",
            duration_seconds=float(limit),
            detail={"argv": argv},
        )

    output = _truncate((completed.stdout or "") + (completed.stderr or ""))
    return VerificationResult(
        ran=True,
        runner=runner_name,
        kind=runner.kind,
        exit_code=completed.returncode,
        passed=completed.returncode == 0,
        output=output,
        duration_seconds=round(time.monotonic() - started, 2),
        detail={"argv": argv, "repo_path": repo_path},
    )
