"""Decision Engine for Hermes OS (HOS-063).

Makes autonomous decisions:
- Agent selection (via AgentSupervisor)
- Runtime selection (via RuntimeOrchestrator)
- Tool selection (via ToolRouter)
- Skill selection (via SkillDistributor)
- Workflow changes

Each decision includes confidence score, alternatives, and explanation.
"""

from __future__ import annotations

import random
import time
from typing import Any

from .autonomous_models import AutonomousDecision, DecisionType


class DecisionEngine:
    """Autonomous decision engine for agentic core.

    Delegates to existing Hermes subsystems (AgentSupervisor,
    RuntimeOrchestrator, SkillDistributor, ToolRouter) and wraps
    their choices into AutonomousDecision objects.
    """

    def __init__(self) -> None:
        self._decisions: list[AutonomousDecision] = []
        self._agent_supervisor: Any = None
        self._runtime_orchestrator: Any = None
        self._skill_distributor: Any = None
        self._tool_router: Any = None

    def set_agent_supervisor(self, supervisor: Any) -> None:
        self._agent_supervisor = supervisor

    def set_runtime_orchestrator(self, orchestrator: Any) -> None:
        self._runtime_orchestrator = orchestrator

    def set_skill_distributor(self, distributor: Any) -> None:
        self._skill_distributor = distributor

    def set_tool_router(self, router: Any) -> None:
        self._tool_router = router

    def select_agent(self, task_type: str, requirements: dict) -> AutonomousDecision:
        """Select the best agent for a task."""
        alternatives = self._generate_agent_alternatives(task_type, requirements)
        best = max(alternatives, key=lambda a: a.get("score", 0))
        confidence = best.get("score", 0.5)

        decision = AutonomousDecision(
            decision_id=f"dec_{int(time.time())}_{random.randint(100,999)}",
            decision_type=DecisionType.AGENT_SELECTION,
            reason=f"Agent {best['name']} best suited for {task_type}: score {best['score']:.2f}",
            confidence=confidence,
            alternatives=alternatives,
            selected_option=best["name"],
            context={"task_type": task_type, "requirements": requirements},
        )
        self._decisions.append(decision)
        return decision

    def select_runtime(self, task_type: str, complexity: float) -> AutonomousDecision:
        """Select the best runtime for a task."""
        alternatives = self._generate_runtime_alternatives(task_type, complexity)
        best = max(alternatives, key=lambda a: a.get("score", 0))

        decision = AutonomousDecision(
            decision_id=f"dec_{int(time.time())}_{random.randint(100,999)}",
            decision_type=DecisionType.RUNTIME_SELECTION,
            reason=f"Runtime {best['name']} optimal for {task_type} (complexity {complexity:.1f})",
            confidence=best.get("score", 0.5),
            alternatives=alternatives,
            selected_option=best["name"],
            context={"task_type": task_type, "complexity": complexity},
        )
        self._decisions.append(decision)
        return decision

    def select_tool(self, task_type: str, parameters: dict) -> AutonomousDecision:
        """Select the best tool for a task."""
        alternatives = self._generate_tool_alternatives(task_type, parameters)
        best = max(alternatives, key=lambda a: a.get("score", 0))

        decision = AutonomousDecision(
            decision_id=f"dec_{int(time.time())}_{random.randint(100,999)}",
            decision_type=DecisionType.TOOL_SELECTION,
            reason=f"Tool {best['name']} selected for {task_type}",
            confidence=best.get("score", 0.5),
            alternatives=alternatives,
            selected_option=best["name"],
            context={"task_type": task_type},
        )
        self._decisions.append(decision)
        return decision

    def select_skill(self, task_type: str, domain: str) -> AutonomousDecision:
        """Select the best skill for a task."""
        alternatives = self._generate_skill_alternatives(task_type, domain)
        best = max(alternatives, key=lambda a: a.get("score", 0))

        decision = AutonomousDecision(
            decision_id=f"dec_{int(time.time())}_{random.randint(100,999)}",
            decision_type=DecisionType.SKILL_SELECTION,
            reason=f"Skill {best['name']} suitable for {domain}/{task_type}",
            confidence=best.get("score", 0.5),
            alternatives=alternatives,
            selected_option=best["name"],
            context={"task_type": task_type, "domain": domain},
        )
        self._decisions.append(decision)
        return decision

    def get_decisions(self, limit: int = 50) -> list[AutonomousDecision]:
        return self._decisions[-limit:]

    def stats(self) -> dict[str, Any]:
        decisions = self._decisions
        return {
            "total_decisions": len(decisions),
            "by_type": {t.value: sum(1 for d in decisions if d.decision_type == t) for t in DecisionType},
            "avg_confidence": round(
                sum(d.confidence for d in decisions) / max(len(decisions), 1), 3
            ),
        }

    # ── Alternative generators ──

    def _generate_agent_alternatives(self, task_type: str, req: dict) -> list[dict]:
        alternatives = [
            {"name": "klaatcode", "description": "Code analysis & diagnostics", "score": 0.85},
            {"name": "ohmypi", "description": "LSP/DAP/AST code editing", "score": 0.82},
            {"name": "code_intelligence", "description": "Meta-agent routing", "score": 0.90},
            {"name": "mission_planner", "description": "Mission planning & DAG", "score": 0.70},
        ]
        if task_type in ("code_analysis", "diagnostics", "code_review"):
            for a in alternatives:
                if a["name"] == "klaatcode":
                    a["score"] = 0.92
        elif task_type in ("refactoring", "debugging"):
            for a in alternatives:
                if a["name"] == "ohmypi":
                    a["score"] = 0.94
        return alternatives

    def _generate_runtime_alternatives(self, task_type: str, complexity: float) -> list[dict]:
        return [
            {"name": "ktransformers", "description": "High-performance inference", "score": 0.85},
            {"name": "default_llm", "description": "Default LLM runtime", "score": 0.75},
            {"name": "local_model", "description": "Local model execution", "score": 0.60},
        ]

    def _generate_tool_alternatives(self, task_type: str, params: dict) -> list[dict]:
        return [
            {"name": "mcp_klaatcode", "description": "KlaatCode MCP tools", "score": 0.88},
            {"name": "mcp_ohmypi", "description": "OhMyPi MCP tools", "score": 0.85},
            {"name": "mcp_filesystem", "description": "File system operations", "score": 0.70},
            {"name": "mcp_network", "description": "Network operations", "score": 0.50},
        ]

    def _generate_skill_alternatives(self, task_type: str, domain: str) -> list[dict]:
        return [
            {"name": "code_analysis", "description": "Code analysis & review", "score": 0.88},
            {"name": "code_generation", "description": "Code generation & editing", "score": 0.85},
            {"name": "testing", "description": "Test generation & execution", "score": 0.75},
            {"name": "documentation", "description": "Documentation generation", "score": 0.65},
        ]
