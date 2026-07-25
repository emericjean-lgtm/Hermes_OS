"""Audit log endpoints — cahier des charges §24.1, feeding the §23.9 view.

Read-only. Records are written by whoever performs an action (see
core/audit_log.record); nothing here creates one, because a log entry
that can be posted by an API caller is not evidence of anything.

`/logs/latency` exists because §22.1 sets latency targets and §28's
T1/T3/T5 test them — until now nothing measured a duration, so those
criteria were unverifiable rather than failing.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.core import audit_log

router = APIRouter()


@router.get("/logs")
async def list_logs(
    session_id: str | None = None,
    agent: str | None = None,
    result: str | None = None,
    limit: int = 100,
) -> list[dict]:
    with audit_log.open_session() as session:
        return [
            audit_log.to_dict(r)
            for r in audit_log.list_records(
                session, session_id=session_id, agent=agent, result=result, limit=limit
            )
        ]


@router.get("/logs/latency")
async def latency(agent: str | None = None) -> dict:
    """Measured latency and throughput. Reports `samples`, and reports it
    even when zero — an empty average shown as a number would read as a
    pass rather than as "never measured"."""
    with audit_log.open_session() as session:
        return audit_log.latency_stats(session, agent=agent)


@router.get("/logs/{session_id}")
async def logs_for_session(session_id: str, limit: int = 100) -> list[dict]:
    with audit_log.open_session() as session:
        return [
            audit_log.to_dict(r)
            for r in audit_log.list_records(session, session_id=session_id, limit=limit)
        ]
