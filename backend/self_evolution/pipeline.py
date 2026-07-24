"""HSE pipeline — composes auto_evaluator/skill_extractor/
reflection_engine into one call: process_task(task, echo).

Deliberately NOT auto-triggered from KronosAgent.update_task(): every
other cross-cutting effect in this project (Aegis's bus trace, workflow
node execution) happens via an explicit call, not a hidden side effect
grafted onto an existing, already-tested CRUD contract — Kronos's
update_task() stays exactly what it was. Call this explicitly instead,
either via the hse_process_task MCP tool / POST /hse/process/{task_id}
(backend/api/routes/hse.py), or from a workflow node.

Takes an EchoAgent instance explicitly (not via get_agent_registry())
so this stays a pure, directly-testable function — the caller (the API
route / MCP tool) is responsible for wiring the real one.
"""
from __future__ import annotations

from backend.agents.echo import EchoAgent
from backend.core.config import get_settings
from backend.memory.skill_library import Skill
from backend.self_evolution import auto_evaluator, reflection_engine, skill_extractor
from backend.tasks.task_manager import Task


def process_task(task: Task, echo: EchoAgent) -> dict:
    """Runs the full pipeline for one (presumably just-completed) task:
    evaluate -> extract a skill on clean success -> reflect (if
    REFLECTION_ENABLED). Safe to call on a non-terminal task — it's just
    a no-op (outcome=None, skill=None, reflection=None) rather than an
    error, so callers don't need to pre-check status themselves."""
    outcome = auto_evaluator.evaluate(task)

    skill: Skill | None = None
    if outcome is True:
        candidate = skill_extractor.extract(task)
        if candidate is not None:
            skill = echo.remember_skill(**candidate)

    reflection: str | None = None
    if get_settings().reflection_enabled:
        reflection_text = reflection_engine.reflect(task)
        if reflection_text is not None:
            reflection = reflection_text
            echo.remember(type_="reflection", content=reflection_text, project_id=task.project_id)

    return {
        "task_id": task.id,
        "outcome": outcome,
        "skill_id": skill.id if skill is not None else None,
        "reflection": reflection,
    }
