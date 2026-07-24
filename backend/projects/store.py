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
from backend.projects.project_manager import Project, ProjectStatus


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
        tags: list[str] | None = None,
    ) -> Project:
        with self._session_factory() as session:
            return project_manager.create_project(
                session, name=name, description=description, root_path=root_path, tags=tags
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
                status=status,
                tags=tags,
            )

    def delete(self, project_id: str) -> bool:
        with self._session_factory() as session:
            return project_manager.delete_project(session, project_id)


@lru_cache
def get_project_store() -> ProjectStore:
    return ProjectStore(get_settings().sqlite_path)
