"""Capability Matcher for the Agent Supervisor (HOS-043).

Matches mission tasks to the most suitable agents based on
capabilities, load, availability, history, and runtime preference.
"""

from __future__ import annotations

from typing import Optional

from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentStatus,
)
from backend.agents.agent_registry import AgentRegistry


class CapabilityMatcher:
    """Matches tasks to agents using multi-criteria scoring.

    Scoring factors (weighted):
    1. Capability match (30%) — does the agent have required skills?
    2. Load (25%) — preference for idle agents
    3. Availability (20%) — agent must be READY
    4. History/success rate (15%) — preference for reliable agents
    5. Runtime preference (10%) — match preferred runtime/model
    """

    # Task type → capability mapping
    _TASK_CAPABILITY_MAP: dict[str, list[AgentCapability]] = {
        "analysis": [AgentCapability.ANALYSIS, AgentCapability.RESEARCH],
        "design": [AgentCapability.DESIGN],
        "implementation": [AgentCapability.CODE_GENERATION],
        "testing": [AgentCapability.TESTING],
        "documentation": [AgentCapability.DOCUMENTATION],
        "deployment": [AgentCapability.DEPLOYMENT],
        "review": [AgentCapability.CODE_REVIEW, AgentCapability.ANALYSIS],
        "planning": [AgentCapability.ANALYSIS, AgentCapability.DESIGN],
        "integration": [AgentCapability.CODE_GENERATION, AgentCapability.DEPLOYMENT],
        "optimization": [AgentCapability.OPTIMIZATION],
        "security": [AgentCapability.SECURITY_AUDIT],
        "custom": [AgentCapability.CUSTOM],
        "task": [AgentCapability.CUSTOM],
    }

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def find_candidates(
        self,
        task_type: str,
        required_skills: Optional[list[str]] = None,
        preferred_runtime: str = "",
        preferred_agent: str = "",
    ) -> list[Agent]:
        """Find candidate agents for a task type.

        Returns agents sorted by match score (best first).
        """
        # Get required capabilities for task type
        required_caps = self._TASK_CAPABILITY_MAP.get(
            task_type, [AgentCapability.CUSTOM]
        )
        if required_skills:
            for skill in required_skills:
                cap = self._skill_to_capability(skill)
                if cap and cap not in required_caps:
                    required_caps.append(cap)

        # Find agents with matching capabilities
        candidates = self._registry.find_by_any_capability(required_caps)
        if not candidates:
            # Fallback: any READY agent
            candidates = self._registry.find_available()

        # Filter by availability
        candidates = [a for a in candidates if a.status == AgentStatus.READY]

        # Score and sort
        scored = [
            (a, self._score_agent(a, required_caps, preferred_runtime, preferred_agent))
            for a in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [a for a, _ in scored]

    def select_best(
        self,
        task_type: str,
        required_skills: Optional[list[str]] = None,
        preferred_runtime: str = "",
        preferred_agent: str = "",
    ) -> Optional[Agent]:
        """Select the single best agent for a task."""
        candidates = self.find_candidates(
            task_type=task_type,
            required_skills=required_skills,
            preferred_runtime=preferred_runtime,
            preferred_agent=preferred_agent,
        )
        return candidates[0] if candidates else None

    def _score_agent(
        self,
        agent: Agent,
        required_caps: list[AgentCapability],
        preferred_runtime: str,
        preferred_agent: str,
    ) -> float:
        """Score an agent's suitability for a task (0.0 - 1.0)."""
        score = 0.0

        # 1. Capability match (30%)
        agent_caps = set(agent.capabilities)
        req_caps = set(required_caps)
        if req_caps:
            cap_score = len(agent_caps & req_caps) / len(req_caps)
            score += 0.30 * cap_score

        # 2. Load (25%) — prefer idle
        if agent.status == AgentStatus.READY and not agent.current_task_id:
            score += 0.25

        # 3. Availability (20%)
        if agent.status == AgentStatus.READY:
            score += 0.20

        # 4. History / success rate (15%)
        score += 0.15 * (agent.success_rate / 100.0)

        # 5. Runtime preference (10%)
        if preferred_runtime and agent.preferred_runtime == preferred_runtime:
            score += 0.10
        elif preferred_agent and agent.agent_id == preferred_agent:
            score += 0.10

        # Additional: profile skill levels bonus
        skill_bonus = sum(agent.profile.skill_levels.values()) / max(
            len(agent.profile.skill_levels), 1
        )
        score = min(1.0, score + 0.05 * skill_bonus)

        return round(score, 3)

    @staticmethod
    def _skill_to_capability(skill: str) -> Optional[AgentCapability]:
        """Map a skill name to a capability."""
        skill_lower = skill.lower()
        mapping = {
            "coding": AgentCapability.CODE_GENERATION,
            "code": AgentCapability.CODE_GENERATION,
            "programming": AgentCapability.CODE_GENERATION,
            "testing": AgentCapability.TESTING,
            "test": AgentCapability.TESTING,
            "writing": AgentCapability.DOCUMENTATION,
            "documentation": AgentCapability.DOCUMENTATION,
            "docs": AgentCapability.DOCUMENTATION,
            "analysis": AgentCapability.ANALYSIS,
            "design": AgentCapability.DESIGN,
            "deployment": AgentCapability.DEPLOYMENT,
            "deploy": AgentCapability.DEPLOYMENT,
            "security": AgentCapability.SECURITY_AUDIT,
            "optimization": AgentCapability.OPTIMIZATION,
            "research": AgentCapability.RESEARCH,
            "review": AgentCapability.CODE_REVIEW,
        }
        return mapping.get(skill_lower)
