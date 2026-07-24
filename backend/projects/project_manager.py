"""Project management — the foundation for scoping work (tasks, memory,
workflows, message-bus trace) per project rather than one global pool.

Not part of the original cahier des charges; added because a single
global namespace for tasks/memory doesn't support managing several
unrelated projects (professional, personal, ...) side by side, which is
the whole point of this module.

Deliberately scoped to *just* the Project entity and its CRUD here.
Linking existing tables (tasks, memory_long, messages, workflows) to a
project via a project_id column is a follow-up step, not done in this
pass — adding a nullable foreign key to four already-shipped,
already-tested tables in the same change as introducing the concept
itself would be a much larger, riskier step than this one.

Mirrors backend/tasks/task_manager.py's shape: a SQLAlchemy model
reusing backend/memory/db.py's Base (same SQLite file as everything
else) plus plain functions taking an explicit Session, wrapped by
backend/projects/store.py's ProjectStore the way KronosAgent wraps
task_manager.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.memory.db import Base


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class InvalidProjectStatusError(ValueError):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    root_path: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default=ProjectStatus.ACTIVE.value)
    tags: Mapped[str] = mapped_column(String, default="")  # comma-separated, e.g. "pro,client-x"
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    @property
    def tags_list(self) -> list[str]:
        return [t for t in self.tags.split(",") if t]


def create_project(
    session: Session,
    *,
    name: str,
    description: str = "",
    root_path: str | None = None,
    tags: list[str] | None = None,
) -> Project:
    now = datetime.now(UTC)
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        root_path=root_path,
        status=ProjectStatus.ACTIVE.value,
        tags=",".join(tags or []),
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def list_projects(
    session: Session, *, status: ProjectStatus | str | None = None, tag: str | None = None
) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc())
    if status is not None:
        try:
            status_value = ProjectStatus(status).value
        except ValueError as exc:
            raise InvalidProjectStatusError(
                f"{status!r} is not a valid project status. "
                f"Known statuses: {[s.value for s in ProjectStatus]}"
            ) from exc
        stmt = stmt.where(Project.status == status_value)

    projects = list(session.execute(stmt).scalars())
    if tag is not None:
        projects = [p for p in projects if tag in p.tags_list]
    return projects


def update_project(
    session: Session,
    project_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    root_path: str | None = None,
    status: ProjectStatus | str | None = None,
    tags: list[str] | None = None,
) -> Project | None:
    project = session.get(Project, project_id)
    if project is None:
        return None

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if root_path is not None:
        project.root_path = root_path
    if status is not None:
        try:
            project.status = ProjectStatus(status).value
        except ValueError as exc:
            raise InvalidProjectStatusError(
                f"{status!r} is not a valid project status. "
                f"Known statuses: {[s.value for s in ProjectStatus]}"
            ) from exc
    if tags is not None:
        project.tags = ",".join(tags)

    project.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project_id: str) -> bool:
    project = session.get(Project, project_id)
    if project is None:
        return False
    session.delete(project)
    session.commit()
    return True
