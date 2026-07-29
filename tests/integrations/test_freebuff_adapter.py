"""HOS-026 sentinel tests — Freebuff Adapter.

Tests the adapter's data structures, connection lifecycle, project
management, prompt generation, response handling, synchronisation,
memory linking, mission-to-plan pipeline, cleanup and thread safety
— all without real network calls.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.integrations.freebuff import (
    FreebuffAdapter,
    FreebuffCapabilities,
    FreebuffConfiguration,
    FreebuffConnectionMode,
    FreebuffError,
    FreebuffProject,
    FreebuffPrompt,
    FreebuffResponse,
    FreebuffSession,
    FreebuffStatus,
)
from backend.agent.task_planner import TaskMission, PlannedTask, TaskPlanner
from backend.events.system_event_bus import SystemEventBus
from backend.memory.unified_memory import MemoryScope


# ============================================================================
# Dataclass tests
# ============================================================================


def test_configuration_defaults() -> None:
    cfg = FreebuffConfiguration()
    assert cfg.mode == FreebuffConnectionMode.API
    assert cfg.api_url == "https://api.freebuff.com/v1"
    assert cfg.timeout == 60.0
    assert cfg.auto_reconnect is True


def test_session_defaults() -> None:
    s = FreebuffSession(session_id="s1")
    assert s.session_id == "s1"
    assert s.mode == FreebuffConnectionMode.API
    assert s.message_count == 0


def test_project_defaults() -> None:
    p = FreebuffProject(project_id="p1", name="Test")
    assert p.project_id == "p1"
    assert p.name == "Test"
    assert p.status == "active"


def test_prompt_defaults() -> None:
    p = FreebuffPrompt(prompt_id="pr1")
    assert p.prompt_id == "pr1"
    assert p.content == ""


def test_response_defaults() -> None:
    r = FreebuffResponse(response_id="r1", prompt_id="pr1")
    assert r.response_id == "r1"
    assert r.success is True
    assert r.error == ""


def test_capabilities_defaults() -> None:
    c = FreebuffCapabilities(available=frozenset({"projects"}))
    assert "projects" in c.available
    assert c.max_prompts_per_project == 1000


def test_connection_mode_values() -> None:
    assert FreebuffConnectionMode.API.value == "api"
    assert FreebuffConnectionMode.TERMINAL.value == "terminal"
    assert FreebuffConnectionMode.CLI.value == "cli"
    assert FreebuffConnectionMode.MCP.value == "mcp"


def test_status_values() -> None:
    assert FreebuffStatus.DISCONNECTED.value == "disconnected"
    assert FreebuffStatus.CONNECTED.value == "connected"
    assert FreebuffStatus.ERROR.value == "error"


# ============================================================================
# Adapter creation
# ============================================================================


def test_adapter_defaults() -> None:
    adapter = FreebuffAdapter()
    assert adapter.status == FreebuffStatus.DISCONNECTED


def test_adapter_with_configuration() -> None:
    cfg = FreebuffConfiguration(
        mode=FreebuffConnectionMode.TERMINAL,
        api_url="http://custom:8080",
        timeout=30.0,
    )
    adapter = FreebuffAdapter(configuration=cfg)
    assert adapter._config.mode == FreebuffConnectionMode.TERMINAL
    assert adapter._config.timeout == 30.0


def test_adapter_initial_state() -> None:
    adapter = FreebuffAdapter()
    assert adapter.list_projects() == []
    assert adapter.status == FreebuffStatus.DISCONNECTED


# ============================================================================
# Connection lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_connect_api_mode() -> None:
    cfg = FreebuffConfiguration(mode=FreebuffConnectionMode.TERMINAL)
    adapter = FreebuffAdapter(configuration=cfg)

    await adapter.connect()
    assert adapter.status == FreebuffStatus.CONNECTED


@pytest.mark.asyncio
async def test_connect_creates_session() -> None:
    cfg = FreebuffConfiguration(mode=FreebuffConnectionMode.TERMINAL)
    adapter = FreebuffAdapter(configuration=cfg)

    await adapter.connect()
    assert len(adapter._sessions) == 1
    session_id = list(adapter._sessions.keys())[0]
    assert adapter._sessions[session_id].mode == FreebuffConnectionMode.TERMINAL


@pytest.mark.asyncio
async def test_disconnect() -> None:
    cfg = FreebuffConfiguration(mode=FreebuffConnectionMode.TERMINAL)
    adapter = FreebuffAdapter(configuration=cfg)

    await adapter.connect()
    assert adapter.status == FreebuffStatus.CONNECTED

    await adapter.disconnect()
    assert adapter.status == FreebuffStatus.DISCONNECTED
    assert adapter._sessions == {}


@pytest.mark.asyncio
async def test_health() -> None:
    cfg = FreebuffConfiguration(mode=FreebuffConnectionMode.TERMINAL)
    adapter = FreebuffAdapter(configuration=cfg)

    await adapter.connect()
    health = await adapter.health()
    assert health["status"] == "connected"
    assert health["mode"] == "terminal"


# ============================================================================
# Project management
# ============================================================================


def test_create_project() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("My Project", description="Test desc")
    assert project.name == "My Project"
    assert project.description == "Test desc"
    assert project.status == "active"


def test_create_project_with_mission() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1", mission_id="mission_123")
    assert project.mission_id == "mission_123"


def test_get_project() -> None:
    adapter = FreebuffAdapter()
    created = adapter.create_project("P1")
    retrieved = adapter.get_project(created.project_id)
    assert retrieved.project_id == created.project_id
    assert retrieved.name == "P1"


def test_get_project_not_found_raises() -> None:
    adapter = FreebuffAdapter()
    with pytest.raises(FreebuffError, match="not found"):
        adapter.get_project("nonexistent")


def test_update_project() -> None:
    adapter = FreebuffAdapter()
    p = adapter.create_project("P1")

    updated = adapter.update_project(p.project_id, name="P2", status="archived")
    assert updated.name == "P2"
    assert updated.status == "archived"
    assert updated.updated_at >= updated.created_at


def test_archive_project() -> None:
    adapter = FreebuffAdapter()
    p = adapter.create_project("P1")
    archived = adapter.archive_project(p.project_id)
    assert archived.status == "archived"


def test_delete_project() -> None:
    adapter = FreebuffAdapter()
    p = adapter.create_project("P1")
    result = adapter.delete_project(p.project_id)
    assert result is True
    assert adapter.list_projects() == []


def test_delete_nonexistent_project() -> None:
    adapter = FreebuffAdapter()
    result = adapter.delete_project("nonexistent")
    assert result is False


def test_list_projects() -> None:
    adapter = FreebuffAdapter()
    adapter.create_project("P1")
    adapter.create_project("P2")
    projects = adapter.list_projects()
    assert len(projects) == 2


def test_list_projects_filtered_by_status() -> None:
    adapter = FreebuffAdapter()
    p1 = adapter.create_project("Active")
    adapter.archive_project(p1.project_id)
    adapter.create_project("Also Active")

    active = adapter.list_projects(status="active")
    assert len(active) == 1

    archived = adapter.list_projects(status="archived")
    assert len(archived) == 1


# ============================================================================
# Prompt generation
# ============================================================================


def test_generate_prompt() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")

    prompt = adapter.generate_prompt(
        project.project_id,
        title="Test prompt",
        context={"instruction": "build a chat app"},
    )
    assert prompt.title == "Test prompt"
    assert prompt.project_id == project.project_id
    assert "build a chat app" in prompt.content


def test_generate_prompt_stores_history() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")
    adapter.generate_prompt(project.project_id, title="Prompt 1")
    adapter.generate_prompt(project.project_id, title="Prompt 2")

    prompts = adapter.list_prompts()
    assert len(prompts) == 2


def test_list_prompts_filtered_by_project() -> None:
    adapter = FreebuffAdapter()
    p1 = adapter.create_project("P1")
    p2 = adapter.create_project("P2")
    adapter.generate_prompt(p1.project_id)
    adapter.generate_prompt(p2.project_id)

    p1_prompts = adapter.list_prompts(project_id=p1.project_id)
    assert len(p1_prompts) == 1


# ============================================================================
# Prompt submission and response
# ============================================================================


def test_submit_prompt_simulated() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")
    prompt = adapter.generate_prompt(project.project_id, title="Hello")

    response = adapter.submit_prompt(prompt)
    assert response.success is True
    assert "Hello" in response.content
    assert response.prompt_id == prompt.prompt_id


def test_submit_prompt_not_connected_raises() -> None:
    adapter = FreebuffAdapter()
    prompt = FreebuffPrompt(prompt_id="pr1", content="test")

    with pytest.raises(FreebuffError, match="not connected"):
        adapter.submit_prompt(prompt, simulate=False)


def test_receive_response() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")
    prompt = adapter.generate_prompt(project.project_id, title="Hi")
    response = adapter.submit_prompt(prompt)

    received = adapter.receive_response(response.response_id)
    assert received.response_id == response.response_id
    assert received.content == response.content


def test_receive_response_not_found_raises() -> None:
    adapter = FreebuffAdapter()
    with pytest.raises(FreebuffError, match="not found"):
        adapter.receive_response("nonexistent")


# ============================================================================
# Synchronisation
# ============================================================================


def test_synchronize_project() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")

    mission = TaskMission(id="m1", title="Test mission", objective="Do something")
    tasks = [
        PlannedTask(id="t1", title="Task 1"),
        PlannedTask(id="t2", title="Task 2"),
    ]

    result = adapter.synchronize_project(
        project.project_id,
        mission=mission,
        tasks=tasks,
    )
    assert result["project_id"] == project.project_id
    assert result["prompt_generated"] is True
    assert result["memory_stored"] is True
    assert result["plan_generated"] is True


def test_synchronize_project_without_mission() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")

    result = adapter.synchronize_project(project.project_id)
    assert result["prompt_generated"] is True
    assert result["memory_stored"] is False


# ============================================================================
# Mission → Freebuff → TaskPlan pipeline
# ============================================================================


def test_mission_to_plan_creates_project_and_prompt() -> None:
    adapter = FreebuffAdapter()
    mission = TaskMission(id="m1", title="Build chat", objective="Create chat app")
    tasks = [
        PlannedTask(id="t1", title="Design", runtime_capability="chat"),
        PlannedTask(id="t2", title="Implement", runtime_capability="code"),
    ]

    result = adapter.mission_to_plan(mission, tasks, project_name="Chat App")
    assert "project" in result
    assert "prompt" in result
    assert "response" in result
    assert "plan" in result
    assert result["project"].name == "Chat App"
    assert result["prompt"].mission_id == "m1"


def test_mission_to_plan_without_auto_submit() -> None:
    adapter = FreebuffAdapter()
    mission = TaskMission(id="m2", title="Test", objective="Test")
    tasks = [PlannedTask(id="t1", title="T1")]

    result = adapter.mission_to_plan(mission, tasks, auto_submit=False)
    assert result["response"] is None


# ============================================================================
# Memory linking
# ============================================================================


def test_link_memory_to_project() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")

    # Store something in memory first.
    adapter._memory.store(
        "Important memory content",
        title="Memory 1",
        scope=MemoryScope.PROJECT,
    )

    count = adapter.link_memory_to_project(project.project_id, scope=MemoryScope.PROJECT)
    assert count == 1

    # The memory should now be linked as a prompt.
    prompts = adapter.list_prompts(project_id=project.project_id)
    assert len(prompts) == 1


# ============================================================================
# Capabilities
# ============================================================================


@pytest.mark.asyncio
async def test_get_capabilities() -> None:
    adapter = FreebuffAdapter()
    caps = await adapter.get_capabilities()
    assert "projects" in caps.available
    assert "prompts" in caps.available
    assert "sync" in caps.available
    assert len(caps.modes) == 4  # API, TERMINAL, CLI, MCP


# ============================================================================
# Events
# ============================================================================


def test_emits_on_project_creation() -> None:
    adapter = FreebuffAdapter()
    events: list[str] = []

    adapter.on_event(lambda evt, _: events.append(evt))
    adapter.create_project("P1")

    assert "freebuff.project_created" in events


def test_emits_on_prompt_submit() -> None:
    adapter = FreebuffAdapter()
    events: list[str] = []

    adapter.on_event(lambda evt, _: events.append(evt))
    project = adapter.create_project("P1")
    prompt = adapter.generate_prompt(project.project_id, title="Hi")
    adapter.submit_prompt(prompt)

    assert "freebuff.prompt_submitted" in events


def test_system_event_bus_integration() -> None:
    bus = SystemEventBus()
    adapter = FreebuffAdapter(event_bus=bus)

    adapter.create_project("P1")

    # Should have published an INTEGRATION event.
    events = bus.query()
    assert len(events) >= 1
    assert events[0].type.name == "INTEGRATION"


# ============================================================================
# Cleanup
# ============================================================================


def test_cleanup_removes_old_entries() -> None:
    adapter = FreebuffAdapter()
    project = adapter.create_project("P1")

    # Create an old prompt by manipulating internal state.
    old_prompt = FreebuffPrompt(
        prompt_id="old_1",
        project_id=project.project_id,
        title="Old",
        created_at=time.time() - 100000,  # Very old
    )
    adapter._prompts["old_1"] = old_prompt

    # Create a recent prompt through normal flow.
    adapter.generate_prompt(project.project_id, title="Recent")

    removed = adapter.cleanup(max_age_s=3600.0)  # 1 hour
    assert removed >= 1  # At least the old one removed

    # Recent prompt should still exist.
    remaining = adapter.list_prompts()
    assert any(p.title == "Recent" for p in remaining)


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_project_operations() -> None:
    adapter = FreebuffAdapter()
    errors: list[Exception] = []

    def creator() -> None:
        for i in range(20):
            try:
                adapter.create_project(f"P{i}")
            except Exception as e:
                errors.append(e)

    def lister() -> None:
        for _ in range(20):
            try:
                adapter.list_projects()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=creator)
    t2 = threading.Thread(target=lister)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert len(adapter.list_projects()) == 20


def test_concurrent_prompt_and_project() -> None:
    adapter = FreebuffAdapter()
    errors: list[Exception] = []

    project = adapter.create_project("Root")

    def prompter() -> None:
        for i in range(30):
            try:
                adapter.generate_prompt(
                    project.project_id,
                    title=f"Prompt {i}",
                )
            except Exception as e:
                errors.append(e)

    def destroyer() -> None:
        for i in range(10):
            try:
                adapter.create_project(f"Extra {i}")
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=prompter)
    t2 = threading.Thread(target=destroyer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
