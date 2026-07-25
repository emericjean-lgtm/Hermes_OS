"""Verification endpoints — cahier des charges §16 (lint / build / tests).

REST face of the whitelisted runners. `GET /verification/runners` is the
only way to discover what may be executed; `POST /verification/run` names
one and can pass nothing else — no command, no arguments.

A refusal comes back as 200 with ran=false and a verdict, not an error
status: at the shipped autonomy_level of "low" that is the *expected*
outcome of every call, and dressing the system's normal safety behaviour
up as a fault would be misleading. Genuine faults keep error codes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import get_agent_registry
from backend.tools import verification
from backend.tools.verification import UnknownRunnerError

router = APIRouter()


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


class RunnerInfo(BaseModel):
    name: str
    kind: str
    description: str


class RunRequest(BaseModel):
    repo_path: str
    runner: str
    timeout: int | None = None
    project_id: str | None = None


class RunResponse(BaseModel):
    ran: bool
    runner: str
    kind: str
    passed: bool
    exit_code: int | None
    timed_out: bool
    verdict: str
    reason: str
    duration_seconds: float
    output: str


@router.get("/verification/runners")
async def list_runners() -> list[RunnerInfo]:
    return [
        RunnerInfo(name=r.name, kind=r.kind, description=r.description)
        for r in verification.list_runners()
    ]


@router.post("/verification/run")
async def run_verification(request: RunRequest) -> RunResponse:
    try:
        result = verification.run(
            _aegis(),
            request.repo_path,
            request.runner,
            timeout=request.timeout,
            project_id=request.project_id,
        )
    except UnknownRunnerError as exc:
        # 400, not 404: the runner name is invalid input, and the response
        # lists the valid ones.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RunResponse(
        ran=result.ran,
        runner=result.runner,
        kind=result.kind,
        passed=result.passed,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        verdict=result.verdict,
        reason=result.reason,
        duration_seconds=result.duration_seconds,
        output=result.output,
    )
