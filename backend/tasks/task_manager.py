"""Task management — cahier des charges §13, §24.3 (tasks table).

Reuses backend/memory/db.py's declarative Base so tasks live in the same
SQLite file as long-term memory — one local database, not two.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class TaskStatus(StrEnum):
    """§13.2 — kept as English identifiers (see repo-wide code-language
    decision); the French cahier des charges wording is in the comments."""

    TODO = "todo"  # à faire
    IN_PROGRESS = "in_progress"  # en cours
    BLOCKED = "blocked"  # bloquée
    AWAITING_VALIDATION = "awaiting_validation"  # en attente de validation
    IN_TEST = "in_test"  # en test
    DONE = "done"  # terminée
    CANCELLED = "cancelled"  # annulée
    REVERSIBLE = "reversible"  # réversible
    PARTIALLY_SUCCESSFUL = "partially_successful"  # partiellement réussie
    TO_RESUME = "to_resume"  # à reprendre


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class InvalidTaskStatusError(ValueError):
    pass


class InvalidTaskPriorityError(ValueError):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, index=True)
    priority: Mapped[str] = mapped_column(String, default=TaskPriority.MEDIUM.value)
    agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    models_used: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    files: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    test_results: Mapped[str] = mapped_column(Text, default="null")  # JSON dict | null
    history: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[dict]

    @property
    def models_used_list(self) -> list[str]:
        return json.loads(self.models_used)

    @property
    def files_list(self) -> list[str]:
        return json.loads(self.files)

    @property
    def test_results_dict(self) -> dict | None:
        return json.loads(self.test_results)

    @property
    def history_list(self) -> list[dict]:
        return json.loads(self.history)


def _append_history(task: Task, note: str) -> None:
    entries = json.loads(task.history)
    entries.append({"timestamp": datetime.now(UTC).isoformat(), "note": note})
    task.history = json.dumps(entries)


def _merge_unique(existing_json: str, new_items: list[str]) -> str:
    existing = json.loads(existing_json)
    for item in new_items:
        if item not in existing:
            existing.append(item)
    return json.dumps(existing)


def create_task(
    session: Session,
    *,
    title: str,
    description: str = "",
    objective: str = "",
    priority: TaskPriority | str = TaskPriority.MEDIUM,
    agent: str | None = None,
) -> Task:
    try:
        priority_value = TaskPriority(priority).value
    except ValueError as exc:
        raise InvalidTaskPriorityError(
            f"{priority!r} is not a valid task priority. "
            f"Known priorities: {[p.value for p in TaskPriority]}"
        ) from exc
    now = datetime.now(UTC)
    task = Task(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        objective=objective,
        status=TaskStatus.TODO.value,
        priority=priority_value,
        agent=agent,
        created_at=now,
        updated_at=now,
        models_used="[]",
        files="[]",
        test_results="null",
        history=json.dumps([{"timestamp": now.isoformat(), "note": "Task created"}]),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_task(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def list_tasks(session: Session, *, status: TaskStatus | str | None = None) -> list[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if status is not None:
        try:
            status_value = TaskStatus(status).value
        except ValueError as exc:
            raise InvalidTaskStatusError(
                f"{status!r} is not a valid task status. "
                f"Known statuses: {[s.value for s in TaskStatus]}"
            ) from exc
        stmt = stmt.where(Task.status == status_value)
    return list(session.execute(stmt).scalars())


def update_task(
    session: Session,
    task_id: str,
    *,
    status: TaskStatus | str | None = None,
    files: list[str] | None = None,
    models_used: list[str] | None = None,
    test_results: dict | None = None,
    note: str | None = None,
) -> Task | None:
    task = session.get(Task, task_id)
    if task is None:
        return None

    if status is not None:
        try:
            new_status = TaskStatus(status)
        except ValueError as exc:
            raise InvalidTaskStatusError(
                f"{status!r} is not a valid task status. "
                f"Known statuses: {[s.value for s in TaskStatus]}"
            ) from exc
        if new_status.value != task.status:
            _append_history(task, f"Status changed: {task.status} -> {new_status.value}")
            task.status = new_status.value

    if files:
        task.files = _merge_unique(task.files, files)
        _append_history(task, f"Files touched: {', '.join(files)}")

    if models_used:
        task.models_used = _merge_unique(task.models_used, models_used)

    if test_results is not None:
        task.test_results = json.dumps(test_results)
        _append_history(task, f"Test results recorded: {test_results}")

    if note:
        _append_history(task, note)

    task.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: str) -> bool:
    task = session.get(Task, task_id)
    if task is None:
        return False
    session.delete(task)
    session.commit()
    return True
