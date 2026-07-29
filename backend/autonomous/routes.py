"""Autonomous Routes for Hermes OS (HOS-063)."""

from __future__ import annotations

from typing import Any

from .autonomous_engine import AutonomousEngine

_engine: AutonomousEngine | None = None


def get_engine() -> AutonomousEngine:
    global _engine
    if _engine is None:
        _engine = AutonomousEngine()
    return _engine


def handle_start_goal(data: dict) -> dict:
    engine = get_engine()
    return engine.start_goal(
        user_request=data["user_request"],
        context=data.get("context"),
    )


def handle_get_goal(goal_id: str) -> dict | None:
    engine = get_engine()
    return engine.get_goal(goal_id)


def handle_pause_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.pause_goal(goal_id)


def handle_resume_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.resume_goal(goal_id)


def handle_cancel_goal(goal_id: str) -> dict:
    engine = get_engine()
    return engine.cancel_goal(goal_id)


def handle_get_timeline(goal_id: str) -> dict:
    engine = get_engine()
    return engine.get_timeline(goal_id)


def handle_get_report(goal_id: str) -> dict | None:
    engine = get_engine()
    return engine.get_report(goal_id)


def handle_get_status() -> dict:
    engine = get_engine()
    return engine.get_status()


AUTONOMOUS_ROUTES = [
    {"path": "/autonomous/start", "method": "POST", "handler": handle_start_goal},
    {"path": "/autonomous/{id}", "method": "GET", "handler": handle_get_goal},
    {"path": "/autonomous/{id}/pause", "method": "POST", "handler": handle_pause_goal},
    {"path": "/autonomous/{id}/resume", "method": "POST", "handler": handle_resume_goal},
    {"path": "/autonomous/{id}/cancel", "method": "POST", "handler": handle_cancel_goal},
    {"path": "/autonomous/{id}/timeline", "method": "GET", "handler": handle_get_timeline},
    {"path": "/autonomous/{id}/report", "method": "GET", "handler": handle_get_report},
    {"path": "/autonomous/status", "method": "GET", "handler": handle_get_status},
]
