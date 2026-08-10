"""ProjectStore — owns the SQLite engine/session factory for Project
CRUD, the same way core/message_bus.py's MessageBus owns its own
(reusing the same SQLite file, see backend/memory/db.py). Not an
"agent" (like Kronos/Aegis/Echo): Projects, like the message bus and
the workflow engine, is core infrastructure with no LLM involvement, so
it isn't registered in config/agents.yaml or built through AgentRegistry
— routes and MCP tools reach it via the module-level get_project_store()
singleton instead.
"""
from __future__ import annotations

from functools import lru_cache

from backend.core.config import get_settings
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.projects import project_manager
from backend.projects.project_manager import Project, ProjectStatus, ValidationStatus


class ProjectStore:
    def __init__(self, sqlite_path: str) -> None:
        engine = make_engine(sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)

    def create(
        self,
        *,
        name: str,
        description: str = "",
        root_path: str | None = None,
        repository: str | None = None,
        branch: str | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        with self._session_factory() as session:
            return project_manager.create_project(
                session, name=name, description=description, root_path=root_path,
                repository=repository, branch=branch, tags=tags,
            )

    def get(self, project_id: str) -> Project | None:
        with self._session_factory() as session:
            return project_manager.get_project(session, project_id)

    def list(
        self, *, status: ProjectStatus | str | None = None, tag: str | None = None
    ) -> list[Project]:
        with self._session_factory() as session:
            return project_manager.list_projects(session, status=status, tag=tag)

    def update(
        self,
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
        with self._session_factory() as session:
            return project_manager.update_project(
                session,
                project_id,
                name=name,
                description=description,
                root_path=root_path,
                repository=repository,
                branch=branch,
                status=status,
                tags=tags,
            )

    def delete(self, project_id: str) -> bool:
        with self._session_factory() as session:
            return project_manager.delete_project(session, project_id)

    def validate(self, project_id: str) -> Project | None:
        """Really probe project.root_path on disk (see
        project_manager.validate_project_path) and persist the result —
        the only source of truth active_validated_project_roots() below
        (and therefore Aegis's dynamic whitelist) trusts."""
        with self._session_factory() as session:
            return project_manager.validate_project(session, project_id)


@lru_cache
def get_project_store() -> ProjectStore:
    return ProjectStore(get_settings().sqlite_path)


def active_validated_project_roots() -> list[str]:
    """Every ACTIVE, validation_status="valid" Project's root_path — the
    single real source of "which local folders has the user actually
    authorized right now". Both AegisAgent._dynamic_allowed_paths
    (agents/aegis.py, the Assistant chat / MCP / file_tools path) and
    Mission's pre-flight security gate (mission/routes.py's
    _check_mission_security) call this same function rather than each
    resolving it independently — a Mission bound to a validated
    workspace must be granted access by the exact same rule a chat
    session bound to it would be, not a second, potentially-drifting
    implementation of "is this project currently authorized".

    Fails closed (empty list) rather than raising if the store is
    briefly unavailable — a missing grant is safe, a crashing security
    check is not."""
    try:
        projects = get_project_store().list(status=ProjectStatus.ACTIVE)
    except Exception:
        return []
    return [
        p.root_path for p in projects
        if p.root_path and p.validation_status == ValidationStatus.VALID.value
    ]
