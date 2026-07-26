"""Kronos — planning & task prioritization agent (cahier des charges §9.1, §13).

Like Aegis and Echo, Kronos is not a chat agent: its contract is the
task_manager CRUD surface below, not respond(). The full vision also has
Kronos turning a plain-language objective into a task breakdown via its
declared model (the "planning" task type in config/models.yaml, resolved
via the orchestrator role) —
that LLM-driven decomposition needs a live Ollama server to exercise
properly and is a natural follow-up once this deterministic base is
validated on real hardware, same as the rest of this project's staging.
"""
from __future__ import annotations

from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings
from backend.core.event_hub import get_event_hub
from backend.core.router import ModelRouter
from backend.memory.db import init_db, make_engine, make_session_factory
from backend.tasks import task_manager
from backend.tasks.task_manager import Task, TaskPriority, TaskStatus



def _announce(task: Task | None, change: str) -> None:
    """Push a task.update event (§24.2).

    Published from Kronos rather than from the REST route on purpose:
    tasks are also changed by MCP tools and by workflow steps, and a
    dashboard fed only by the route would silently miss exactly the
    changes an agent made on its own — which is the case that motivated
    the real-time view in the first place.
    """
    if task is None:
        return
    get_event_hub().publish("task.update", {
        "change": change,
        "id": task.id,
        "title": task.title,
        "status": getattr(task.status, "value", task.status),
        "priority": getattr(task.priority, "value", task.priority),
        "agent": task.agent,
        "project_id": task.project_id,
    })


class KronosAgent:
    name: ClassVar[str] = "kronos"

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
    ) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config

        settings = get_settings()
        engine = make_engine(settings.sqlite_path)
        init_db(engine)
        self._session_factory = make_session_factory(engine)

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        objective: str = "",
        priority: TaskPriority | str = TaskPriority.MEDIUM,
        agent: str | None = None,
        project_id: str | None = None,
    ) -> Task:
        with self._session_factory() as session:
            task = task_manager.create_task(
                session,
                title=title,
                description=description,
                objective=objective,
                priority=priority,
                agent=agent,
                project_id=project_id,
            )
            _announce(task, "created")
            return task

    def get_task(self, task_id: str) -> Task | None:
        with self._session_factory() as session:
            return task_manager.get_task(session, task_id)

    def list_tasks(
        self, *, status: TaskStatus | str | None = None, project_id: str | None = None
    ) -> list[Task]:
        with self._session_factory() as session:
            return task_manager.list_tasks(session, status=status, project_id=project_id)

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | str | None = None,
        files: list[str] | None = None,
        models_used: list[str] | None = None,
        test_results: dict | None = None,
        note: str | None = None,
        project_id: str | None = None,
    ) -> Task | None:
        with self._session_factory() as session:
            task = task_manager.update_task(
                session,
                task_id,
                status=status,
                files=files,
                models_used=models_used,
                test_results=test_results,
                note=note,
                project_id=project_id,
            )
            _announce(task, "updated")
            return task

    def delete_task(self, task_id: str) -> bool:
        with self._session_factory() as session:
            task = task_manager.get_task(session, task_id)
            deleted = task_manager.delete_task(session, task_id)
        if deleted:
            _announce(task, "deleted")
        return deleted
