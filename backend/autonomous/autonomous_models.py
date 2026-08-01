"""Autonomous Agentic Core models for Hermes OS (HOS-063)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GoalStatus(str, Enum):
    RECEIVED = "received"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    LEARNING = "learning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class DecisionType(str, Enum):
    AGENT_SELECTION = "agent_selection"
    RUNTIME_SELECTION = "runtime_selection"
    TOOL_SELECTION = "tool_selection"
    SKILL_SELECTION = "skill_selection"
    WORKFLOW_CHANGE = "workflow_change"


@dataclass
class AutonomousGoal:
    """A human goal interpreted by the autonomous system."""
    goal_id: str = ""
    user_request: str = ""
    interpreted_goal: str = ""
    contraints: dict[str, Any] = field(default_factory=dict)
    priority: str = "normal"
    status: GoalStatus = GoalStatus.RECEIVED
    language: str = ""
    domain: str = ""
    complexity: float = 0.5
    estimated_duration_s: float = 0.0
    # Which project this goal operates on (HOS-067) — a local checkout
    # (validated against Aegis's ALLOWED_PATHS whitelist before planning)
    # and/or a GitHub repository, threaded into PlanningRequest.repository/
    # branch/context so the real decomposition prompt and any file/git tools
    # a task uses know which project they're working on. Both empty means
    # "no specific project" — every existing caller keeps working unchanged.
    local_path: str = ""
    repository: str = ""
    branch: str = ""
    # Real prior-experience summary (HOS-067) — from
    # MemoryManager.recommend_for_mission(), gathered before planning so it
    # can be threaded into the decomposition prompt. Empty string is honest
    # on a fresh deployment with no history yet, not an error.
    knowledge_context: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "user_request": self.user_request,
            "interpreted_goal": self.interpreted_goal,
            "contraints": self.contraints,
            "priority": self.priority,
            "status": self.status.value,
            "language": self.language,
            "domain": self.domain,
            "complexity": self.complexity,
            "estimated_duration_s": self.estimated_duration_s,
            "local_path": self.local_path,
            "repository": self.repository,
            "branch": self.branch,
            "knowledge_context": self.knowledge_context,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AutonomousSession:
    """A full autonomous execution session."""
    session_id: str = ""
    goal_id: str = ""
    mission_id: str = ""
    active_agents: list[str] = field(default_factory=list)
    runtime: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    status: GoalStatus = GoalStatus.RECEIVED
    timeline: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "mission_id": self.mission_id,
            "active_agents": self.active_agents,
            "runtime": self.runtime,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "timeline_entries": len(self.timeline),
        }


@dataclass
class AutonomousDecision:
    """A decision made during autonomous execution."""
    decision_id: str = ""
    decision_type: DecisionType = DecisionType.AGENT_SELECTION
    reason: str = ""
    confidence: float = 0.0
    alternatives: list[dict] = field(default_factory=list)
    selected_option: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "alternatives_count": len(self.alternatives),
            "selected": self.selected_option,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AutonomousReport:
    """Final report from an autonomous goal execution."""
    goal_id: str = ""
    user_request: str = ""
    interpreted_goal: str = ""
    execution_summary: str = ""
    results: dict[str, Any] = field(default_factory=dict)
    improvements: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    total_duration_ms: float = 0.0
    agents_used: list[str] = field(default_factory=list)
    runtimes_used: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    success: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "user_request": self.user_request,
            "interpreted_goal": self.interpreted_goal,
            "execution_summary": self.execution_summary,
            "results": self.results,
            "improvements": self.improvements,
            "lessons": self.lessons,
            "decisions": self.decisions,
            "total_duration_ms": self.total_duration_ms,
            "agents_used": self.agents_used,
            "runtimes_used": self.runtimes_used,
            "tools_used": self.tools_used,
            "success": self.success,
        }


AUTONOMOUS_EVENTS = {
    "goal_received": "autonomous.goal.received",
    "goal_analyzed": "autonomous.goal.analyzed",
    "plan_created": "autonomous.plan.created",
    "agent_selected": "autonomous.agent.selected",
    "execution_started": "autonomous.execution.started",
    "execution_completed": "autonomous.execution.completed",
    "learning_completed": "autonomous.learning.completed",
    "goal_failed": "autonomous.goal.failed",
    "decision_made": "autonomous.decision.made",
    # HOS-067: a REQUIRE_HUMAN_VALIDATION verdict from Aegis pauses the goal
    # instead of failing it — distinct from goal_failed so the Cockpit can
    # tell "needs a human" from "something went wrong".
    "goal_paused": "autonomous.goal.paused",
}

# Heuristic domain/task-type mappings for goal interpretation
GOAL_PATTERNS: dict[str, dict] = {
    "web_app": {"domain": "web", "likely_agents": ["klaatcode", "ohmypi"], "complexity": 0.7},
    "api": {"domain": "backend", "likely_agents": ["klaatcode", "ohmypi"], "complexity": 0.6},
    "data": {"domain": "data", "likely_agents": ["klaatcode"], "complexity": 0.5},
    "refactor": {"domain": "code", "likely_agents": ["ohmypi", "klaatcode"], "complexity": 0.6},
    "debug": {"domain": "code", "likely_agents": ["ohmypi"], "complexity": 0.5},
    "document": {"domain": "docs", "likely_agents": ["klaatcode"], "complexity": 0.3},
    "test": {"domain": "testing", "likely_agents": ["klaatcode", "ohmypi"], "complexity": 0.5},
    "deploy": {"domain": "devops", "likely_agents": ["klaatcode"], "complexity": 0.8},
    "analyze": {"domain": "analysis", "likely_agents": ["klaatcode"], "complexity": 0.4},
    "learn": {"domain": "learning", "likely_agents": ["klaatcode"], "complexity": 0.5},
}
