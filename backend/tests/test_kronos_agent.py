from __future__ import annotations

from backend.tasks.task_manager import TaskStatus


def test_create_and_get_task(kronos_agent):
    task = kronos_agent.create_task(title="Refactor auth", agent="atlas")
    fetched = kronos_agent.get_task(task.id)
    assert fetched.title == "Refactor auth"
    assert fetched.agent == "atlas"


def test_update_task_status(kronos_agent):
    task = kronos_agent.create_task(title="x")
    updated = kronos_agent.update_task(task.id, status=TaskStatus.IN_PROGRESS)
    assert updated.status == "in_progress"


def test_delete_task(kronos_agent):
    task = kronos_agent.create_task(title="x")
    assert kronos_agent.delete_task(task.id) is True
    assert kronos_agent.get_task(task.id) is None


def test_list_tasks_filters_by_status(kronos_agent):
    kronos_agent.create_task(title="a")
    b = kronos_agent.create_task(title="b")
    kronos_agent.update_task(b.id, status="blocked")

    assert [t.title for t in kronos_agent.list_tasks(status="todo")] == ["a"]
    assert [t.title for t in kronos_agent.list_tasks(status="blocked")] == ["b"]


def test_list_tasks_filters_by_project_id(kronos_agent):
    kronos_agent.create_task(title="a", project_id="proj-1")
    kronos_agent.create_task(title="b", project_id="proj-2")

    assert [t.title for t in kronos_agent.list_tasks(project_id="proj-1")] == ["a"]


def test_tasks_persist_across_agent_instances(kronos_agent, models_config, fake_ollama_client):
    from backend.agents.kronos import KronosAgent
    from backend.core.router import ModelRouter

    kronos_agent.create_task(title="persisted task")

    router = ModelRouter(models_config)
    second_agent = KronosAgent(fake_ollama_client, router, models_config)
    assert [t.title for t in second_agent.list_tasks()] == ["persisted task"]
