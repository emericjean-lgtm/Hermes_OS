from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from backend.memory.skill_library import Skill
from backend.self_evolution import auto_evaluator, progression_tracker, reflection_engine, skill_extractor
from backend.self_evolution.pipeline import process_task
from backend.tasks.task_manager import Task, TaskStatus


def _task(*, status: str, title: str = "Refactor auth", objective: str = "", history=None, project_id=None) -> Task:
    now = datetime.now(UTC)
    return Task(
        id="task-1",
        project_id=project_id,
        title=title,
        description="Some description",
        objective=objective,
        status=status,
        priority="medium",
        agent=None,
        created_at=now,
        updated_at=now,
        models_used="[]",
        files="[]",
        test_results="null",
        history=json.dumps(history or [{"timestamp": now.isoformat(), "note": "Task created"}]),
    )


# ── auto_evaluator ──────────────────────────────────────────────────────


def test_evaluate_done_is_success():
    assert auto_evaluator.evaluate(_task(status=TaskStatus.DONE)) is True


def test_evaluate_cancelled_is_failure():
    assert auto_evaluator.evaluate(_task(status=TaskStatus.CANCELLED)) is False


def test_evaluate_partially_successful_is_neither():
    assert auto_evaluator.evaluate(_task(status=TaskStatus.PARTIALLY_SUCCESSFUL)) is None


def test_evaluate_non_terminal_is_none():
    assert auto_evaluator.evaluate(_task(status=TaskStatus.IN_PROGRESS)) is None


def test_is_terminal():
    assert auto_evaluator.is_terminal(_task(status=TaskStatus.DONE)) is True
    assert auto_evaluator.is_terminal(_task(status=TaskStatus.TODO)) is False


# ── skill_extractor ─────────────────────────────────────────────────────


def test_extract_builds_candidate_from_task():
    task = _task(
        status=TaskStatus.DONE,
        objective="Ship the feature",
        history=[{"timestamp": "t1", "note": "Task created"}, {"timestamp": "t2", "note": "Status changed: todo -> done"}],
        project_id="proj-1",
    )
    candidate = skill_extractor.extract(task)
    assert candidate["name"] == "Refactor auth"
    assert candidate["project_id"] == "proj-1"
    assert candidate["source_task_id"] == "task-1"
    assert "Ship the feature" in candidate["procedure"]
    assert "Task created" in candidate["procedure"]
    # Starts strictly between the floor and the auto-validate threshold
    # (defaults 0.30/0.95) — an untested procedure shouldn't be born
    # already "validated".
    assert 0.30 < candidate["confidence"] < 0.95


def test_extract_returns_none_for_blank_title():
    task = _task(status=TaskStatus.DONE, title="   ")
    assert skill_extractor.extract(task) is None


# ── reflection_engine ────────────────────────────────────────────────────


def test_reflect_done_task():
    task = _task(status=TaskStatus.DONE, title="Ship it")
    reflection = reflection_engine.reflect(task)
    assert "Ship it" in reflection
    assert "succeeded" in reflection


def test_reflect_cancelled_task():
    task = _task(status=TaskStatus.CANCELLED, title="Abandoned")
    reflection = reflection_engine.reflect(task)
    assert "was cancelled" in reflection


def test_reflect_non_terminal_task_returns_none():
    task = _task(status=TaskStatus.IN_PROGRESS)
    assert reflection_engine.reflect(task) is None


# ── progression_tracker ──────────────────────────────────────────────────


def test_compute_progression_success_rate_and_skill_buckets():
    tasks = [
        _task(status=TaskStatus.DONE),
        _task(status=TaskStatus.DONE),
        _task(status=TaskStatus.CANCELLED),
        _task(status=TaskStatus.IN_PROGRESS),  # not terminal, excluded from the rate
    ]
    now = datetime.now(UTC)
    skills = [
        Skill(id="s1", project_id=None, name="A", description="", procedure="", confidence=0.97, decay=0.0,
              uses=0, successes=0, tags="", source_task_id=None, created_at=now, updated_at=now),
        Skill(id="s2", project_id=None, name="B", description="", procedure="", confidence=0.5, decay=0.0,
              uses=0, successes=0, tags="", source_task_id=None, created_at=now, updated_at=now),
        Skill(id="s3", project_id=None, name="C", description="", procedure="", confidence=0.1, decay=0.0,
              uses=0, successes=0, tags="", source_task_id=None, created_at=now, updated_at=now),
    ]

    progression = progression_tracker.compute_progression(tasks, skills)

    assert progression["tasks_total"] == 4
    assert progression["tasks_terminal"] == 3
    assert progression["tasks_succeeded"] == 2
    assert progression["success_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert progression["skills_total"] == 3
    assert progression["skills_validated"] == 1
    assert progression["skills_in_review"] == 1
    assert progression["skills_below_floor"] == 1


def test_compute_progression_handles_empty_input():
    progression = progression_tracker.compute_progression([], [])
    assert progression["success_rate"] is None
    assert progression["average_skill_confidence"] is None


# ── pipeline ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_task_extracts_skill_on_success(echo_agent):
    task = _task(status=TaskStatus.DONE, title="Ship it", project_id="proj-1")

    result = process_task(task, echo_agent)

    assert result["outcome"] is True
    assert result["skill_id"] is not None
    skill = echo_agent.get_skill(result["skill_id"])
    assert skill.name == "Ship it"
    assert skill.source_task_id == "task-1"
    assert result["reflection"] is None  # REFLECTION_ENABLED defaults to False
    assert result["deduplicated"] is False


@pytest.mark.asyncio
async def test_process_task_reinforces_existing_skill_with_same_name_instead_of_duplicating(echo_agent):
    first_task = _task(status=TaskStatus.DONE, title="Ship it", project_id="proj-1")
    first = process_task(first_task, echo_agent)
    assert first["deduplicated"] is False

    second_task = _task(status=TaskStatus.DONE, title="ship it", project_id="proj-1")  # case differs
    second = process_task(second_task, echo_agent)

    assert second["deduplicated"] is True
    assert second["skill_id"] == first["skill_id"]  # same skill, not a new one
    assert len(echo_agent.list_skills(project_id="proj-1")) == 1

    skill = echo_agent.get_skill(second["skill_id"])
    assert skill.uses == 1
    assert skill.successes == 1


@pytest.mark.asyncio
async def test_process_task_same_name_different_project_is_not_deduplicated(echo_agent):
    first = process_task(_task(status=TaskStatus.DONE, title="Ship it", project_id="proj-1"), echo_agent)
    second = process_task(_task(status=TaskStatus.DONE, title="Ship it", project_id="proj-2"), echo_agent)

    assert second["deduplicated"] is False
    assert second["skill_id"] != first["skill_id"]
    assert len(echo_agent.list_skills()) == 2


@pytest.mark.asyncio
async def test_process_task_no_skill_on_failure(echo_agent):
    task = _task(status=TaskStatus.CANCELLED)

    result = process_task(task, echo_agent)

    assert result["outcome"] is False
    assert result["skill_id"] is None
    assert echo_agent.list_skills() == []


@pytest.mark.asyncio
async def test_process_task_is_a_noop_for_non_terminal_task(echo_agent):
    task = _task(status=TaskStatus.IN_PROGRESS)

    result = process_task(task, echo_agent)

    assert result == {
        "task_id": "task-1",
        "outcome": None,
        "skill_id": None,
        "deduplicated": False,
        "reflection": None,
    }


@pytest.mark.asyncio
async def test_process_task_reflects_when_enabled(monkeypatch, echo_agent):
    from backend.core.config import get_settings

    monkeypatch.setenv("REFLECTION_ENABLED", "true")
    get_settings.cache_clear()
    try:
        task = _task(status=TaskStatus.DONE, title="Ship it")
        result = process_task(task, echo_agent)
        assert result["reflection"] is not None
        assert "Ship it" in result["reflection"]
        reflections = echo_agent.list_memories(type_="reflection")
        assert len(reflections) == 1
    finally:
        get_settings.cache_clear()
