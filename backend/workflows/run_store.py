"""Persisted workflow run state — makes resuming past a human_validation
gate possible without re-executing already-finished nodes.

Plain SQLAlchemy CRUD, same split as task_manager.py/skill_library.py:
storage only, no policy — WorkflowEngine (engine.py) decides what to do
with a loaded run, this module just remembers/recalls it.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String)
    node_results: Mapped[str] = mapped_column(Text)  # JSON: {node_id: {status, result, error}}
    pending_nodes: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    # Cumulative across every resume call, not just the latest one — a
    # node approved on one resume stays approved on the next.
    approved_nodes: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    @property
    def node_results_dict(self) -> dict:
        return json.loads(self.node_results)

    @property
    def pending_nodes_list(self) -> list[str]:
        return json.loads(self.pending_nodes)

    @property
    def approved_nodes_set(self) -> set[str]:
        return set(json.loads(self.approved_nodes))


def save_run(
    session: Session,
    *,
    run_id: str,
    workflow_id: str,
    project_id: str | None,
    status: str,
    node_results: dict,
    pending_nodes: list[str],
    approved_nodes: set[str],
) -> WorkflowRunRecord:
    """Upsert by run_id — the first call for a given id creates it, every
    subsequent one (a resume) overwrites it with the latest state."""
    now = datetime.now(UTC)
    record = session.get(WorkflowRunRecord, run_id)
    if record is None:
        record = WorkflowRunRecord(id=run_id, created_at=now)
        session.add(record)
    record.workflow_id = workflow_id
    record.project_id = project_id
    record.status = status
    record.node_results = json.dumps(node_results)
    record.pending_nodes = json.dumps(pending_nodes)
    record.approved_nodes = json.dumps(sorted(approved_nodes))
    record.updated_at = now
    session.commit()
    session.refresh(record)
    return record


def get_run(session: Session, run_id: str) -> WorkflowRunRecord | None:
    return session.get(WorkflowRunRecord, run_id)


def list_runs(
    session: Session, *, workflow_id: str | None = None, project_id: str | None = None
) -> list[WorkflowRunRecord]:
    stmt = select(WorkflowRunRecord).order_by(WorkflowRunRecord.created_at.desc())
    if workflow_id is not None:
        stmt = stmt.where(WorkflowRunRecord.workflow_id == workflow_id)
    if project_id is not None:
        stmt = stmt.where(WorkflowRunRecord.project_id == project_id)
    return list(session.execute(stmt).scalars())
