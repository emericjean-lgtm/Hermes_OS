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

Workspace/Filesystem tool layer: a Project *is* the authorized-workspace
concept the filesystem tools are scoped to — not a second entity. root_path
gains a real, on-disk-tested validation (validate_project_path/validate_project
below) and repository/branch fields mirroring Mission's existing three-field
project binding (types/hermes.ts's local_path/repository/branch, HOS-068).
Aegis (security/aegis_engine.py) treats an ACTIVE, validation_status="valid"
Project's root_path as part of its dynamic whitelist — see
AegisAgent._dynamic_allowed_paths() in agents/aegis.py. The four new columns
are nullable, so backend/memory/db.py's additive _add_missing_columns picks
them up on an existing database with a plain ALTER TABLE, no migration tool
needed (same mechanism that added memory_long.project_id before this).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from sqlalchemy import Boolean, DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.core.event_hub import get_event_hub
from backend.memory.db import Base

# --------------------------------------------------------------------
"""L'enregistrement et la validation d'un workspace autorisé (HOS-181)."""
PROJECT_EVENTS: dict[str, str] = {
    "registered": "project.registered",
    "validated": "project.validated",
}


def _publish(event_type: str, payload: dict) -> None:
    """Best-effort notification, same never-fail contract as
    tools/file_tools.py's own _publish — a dashboard hiccup must never
    fail the real registration/validation it is reporting on."""
    try:
        get_event_hub().publish(event_type, payload)
    except Exception:
        pass


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ValidationStatus(StrEnum):
    UNVALIDATED = "unvalidated"
    VALID = "valid"
    INVALID = "invalid"


class InvalidProjectStatusError(ValueError):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    root_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # GitHub binding — independent of root_path, fillable together (a local
    # checkout AND its remote), mirroring Mission.repository/branch
    # (HOS-068) rather than the old one-or-the-other UI/data model.
    repository: Mapped[str | None] = mapped_column(String, nullable=True)
    branch: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default=ProjectStatus.ACTIVE.value)
    # Real, on-disk-tested state — never set from the frontend or from a
    # model's own claim (see validate_project_path). "unvalidated" until
    # POST /projects/{id}/validate actually probes the path.
    validation_status: Mapped[str | None] = mapped_column(String, nullable=True)
    validated_accessible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validated_readable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validated_writable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validation_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    repository: str | None = None,
    branch: str | None = None,
    tags: list[str] | None = None,
) -> Project:
    now = datetime.now(UTC)
    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        root_path=root_path,
        repository=repository,
        branch=branch,
        status=ProjectStatus.ACTIVE.value,
        validation_status=ValidationStatus.UNVALIDATED.value if root_path else None,
        tags=",".join(tags or []),
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    _publish("project.registered", {
        "project_id": project.id, "name": project.name, "root_path": project.root_path,
        "repository": project.repository,
    })
    return project


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def list_projects(
    session: Session, *, status: ProjectStatus | str | None = None, tag: str | None = None
) -> list[Project]:
    # `id` départage les dates égales (HOS-112). Sous Windows l'horloge
    # système avance par pas d'environ 15,6 ms : deux projets créés coup sur
    # coup portent le même `created_at`, et un tri sur cette seule colonne
    # laisse alors l'ordre à la discrétion du moteur — la liste pouvait se
    # réordonner d'un affichage à l'autre sans que rien n'ait changé.
    # L'ordre entre ex aequo n'a pas de sens intrinsèque ; ce qui compte est
    # qu'il soit le même à chaque requête.
    stmt = select(Project).order_by(Project.created_at.desc(), Project.id.desc())
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
    repository: str | None = None,
    branch: str | None = None,
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
    if root_path is not None and root_path != project.root_path:
        project.root_path = root_path
        # A changed path invalidates whatever was probed before — Aegis
        # must not keep trusting a validation result for a path that no
        # longer applies. Re-validate explicitly (POST .../validate)
        # before this project can grant filesystem access again.
        project.validation_status = ValidationStatus.UNVALIDATED.value
        project.validated_accessible = None
        project.validated_readable = None
        project.validated_writable = None
        project.validation_detail = None
        project.validated_at = None
    if repository is not None:
        project.repository = repository
    if branch is not None:
        project.branch = branch
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


class PathValidationResult(TypedDict):
    accessible: bool
    readable: bool
    writable: bool
    detail: str
    resolved_path: str | None


def validate_project_path(root_path: str) -> PathValidationResult:
    """Really test root_path on disk — never a claim, always a measurement
    (cahier des charges' "never fabricate a result" principle, applied to
    workspace registration). Readable is proven by actually listing the
    directory, not by os.access alone (unreliable on some Windows ACL
    configurations); writable is proven by actually creating, reading back
    and deleting a small probe file, not by permission bits alone.
    """
    try:
        candidate = Path(root_path).expanduser()
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return {
            "accessible": False, "readable": False, "writable": False,
            "detail": "Chemin invalide.", "resolved_path": None,
        }

    if not resolved.exists():
        return {
            "accessible": False, "readable": False, "writable": False,
            "detail": f"{resolved} n'existe pas.", "resolved_path": str(resolved),
        }
    if not resolved.is_dir():
        return {
            "accessible": False, "readable": False, "writable": False,
            "detail": f"{resolved} n'est pas un dossier.", "resolved_path": str(resolved),
        }

    readable = True
    try:
        list(resolved.iterdir())
    except OSError:
        readable = False

    writable = False
    probe = resolved / f".hermes_validate_{uuid.uuid4().hex}.tmp"
    try:
        probe.write_text("hermes-validate", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "hermes-validate"
    except OSError:
        writable = False
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass

    accessible = readable
    parts = ["accessible" if accessible else "inaccessible"]
    parts.append("lecture OK" if readable else "lecture refusée")
    parts.append("écriture OK" if writable else "écriture refusée")
    return {
        "accessible": accessible, "readable": readable, "writable": writable,
        "detail": ", ".join(parts), "resolved_path": str(resolved),
    }


def validate_project(session: Session, project_id: str) -> Project | None:
    """Probe project.root_path for real and persist the result — the only
    place validation_status is ever written. Normalizes root_path to the
    resolved absolute form on success, so what Aegis's whitelist checks
    against later is exactly what was tested here (cahier des charges'
    root_path handling: "normalise et résous immédiatement le chemin")."""
    project = session.get(Project, project_id)
    if project is None:
        return None

    if not project.root_path:
        project.validation_status = ValidationStatus.INVALID.value
        project.validated_accessible = False
        project.validated_readable = False
        project.validated_writable = False
        project.validation_detail = "Aucun dossier local associé à ce projet."
        project.validated_at = datetime.now(UTC)
        session.commit()
        session.refresh(project)
        _publish("project.validated", {
            "project_id": project.id, "validation_status": project.validation_status,
            "detail": project.validation_detail,
        })
        return project

    result = validate_project_path(project.root_path)
    project.validation_status = (
        ValidationStatus.VALID.value if result["accessible"] else ValidationStatus.INVALID.value
    )
    project.validated_accessible = result["accessible"]
    project.validated_readable = result["readable"]
    project.validated_writable = result["writable"]
    project.validation_detail = result["detail"]
    project.validated_at = datetime.now(UTC)
    if result["accessible"] and result["resolved_path"]:
        project.root_path = result["resolved_path"]
    session.commit()
    session.refresh(project)
    _publish("project.validated", {
        "project_id": project.id, "validation_status": project.validation_status,
        "root_path": project.root_path, "detail": project.validation_detail,
    })
    return project
