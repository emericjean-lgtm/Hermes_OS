"""Autonomous Goal Interpreter for Hermes OS (HOS-063).

Transforms human requests into structured goals with constraints,
tasks, and resource requirements.

Uses Memory Retrieval Engine, Knowledge Graph, and Experience Manager
to enrich interpretation with past learnings.
"""

from __future__ import annotations

import random
import time
from typing import Any

from .autonomous_models import AutonomousGoal, GOAL_PATTERNS, GoalStatus


class AutonomousInterpreter:
    """Interprets human goals into structured autonomous objectives.

    Analyzes user request, identifies domain, complexity, required
    agents, and constraints. Integrates with Memory for context.
    """

    def __init__(self) -> None:
        self._memory_manager: Any = None
        self._history: list[dict] = []

    def set_memory_manager(self, mm: Any) -> None:
        self._memory_manager = mm

    def interpret(self, user_request: str, context: dict[str, Any] | None = None) -> AutonomousGoal:
        """Transform a human request into an AutonomousGoal."""
        ctx = context or {}
        domain, language, constraints = self._analyze_request(user_request)
        complexity = self._estimate_complexity(user_request, domain)

        goal = AutonomousGoal(
            goal_id=f"goal_{int(time.time())}_{random.randint(100,999)}",
            user_request=user_request,
            interpreted_goal=self._generate_interpretation(user_request, domain),
            contraints=constraints,
            priority=ctx.get("priority", "normal"),
            status=GoalStatus.ANALYZING,
            language=language,
            domain=domain,
            complexity=complexity,
        )

        if self._memory_manager:
            try:
                similar = self._memory_manager.search(
                    f"goal:{user_request[:50]}", mode="keyword"
                )
                if similar:
                    goal.estimated_duration_s = self._estimate_from_history(similar)
            except Exception:
                pass

        self._history.append({
            "goal_id": goal.goal_id,
            "request": user_request[:100],
            "domain": domain,
            "complexity": complexity,
        })

        return goal

    def get_history(self, limit: int = 50) -> list[dict]:
        return self._history[-limit:]

    # ── Private ──

    def _analyze_request(self, text: str) -> tuple[str, str, dict]:
        text_lower = text.lower()
        domain = "general"
        language = "python"
        constraints: dict[str, Any] = {}

        domain_keywords = {
            "web": ["web", "app", "frontend", "site", "interface", "ui", "dashboard"],
            "backend": ["api", "service", "server", "backend", "endpoint", "rest"],
            "data": ["data", "analyse", "analytics", "pipeline", "etl", "database"],
            "code": ["refactor", "clean", "optimize", "rewrite", "migrate", "debug"],
            "testing": ["test", "qa", "quality", "coverage", "assert"],
            "devops": ["deploy", "ci/cd", "docker", "kubernetes", "infra"],
            "docs": ["doc", "readme", "manual", "guide", "tutorial"],
            "learning": ["learn", "study", "research", "explore"],
        }

        # Score-based matching: pick the domain with the most keyword hits
        # Code keywords (debug, refactor, optimize) are stronger intent signals
        # than technical nouns (endpoint, database), so give code a bonus
        scores: dict[str, int] = {}
        for d, keywords in domain_keywords.items():
            count = sum(1 for kw in keywords if f" {kw} " in f" {text_lower} ")
            if count > 0:
                multiplier = 2.0 if d == "code" else 1.0
                scores[d] = int(count * multiplier)

        if scores:
            domain = max(scores, key=scores.get)

        lang_keywords = {
            "python": ["python", "django", "flask", "pandas"],
            "typescript": ["typescript", "ts", "angular", "react", "next"],
            "javascript": ["javascript", "js", "node", "express"],
            "rust": ["rust", "cargo"],
            "go": ["golang", "go "],
        }
        for lang, keywords in lang_keywords.items():
            if any(kw in text_lower for kw in keywords):
                language = lang
                break

        if any(w in text_lower for w in ["urgent", "critical", "asap", "important"]):
            constraints["priority"] = "high"
        if any(w in text_lower for w in ["secure", "security", "safe"]):
            constraints["security_required"] = True

        return domain, language, constraints

    def _generate_interpretation(self, text: str, domain: str) -> str:
        return f"Interpreted goal: {text[:120]}. Domain: {domain}. Analysis complete."

    def _estimate_complexity(self, text: str, domain: str) -> float:
        base = 0.3
        if len(text) > 200:
            base += 0.2
        if len(text) > 500:
            base += 0.2
        complex_keywords = ["full", "complete", "integrated", "complex", "large",
                           "microservices", "distributed", "production"]
        if any(kw in text.lower() for kw in complex_keywords):
            base += 0.15
        return min(1.0, base + random.uniform(-0.1, 0.1))

    def _estimate_from_history(self, similar_goals: list) -> float:
        try:
            durations = [g.metadata.get("duration_ms", 0) for g in similar_goals
                        if hasattr(g, "metadata")]
            if durations:
                return sum(durations) / len(durations) / 1000.0
        except Exception:
            pass
        return 0.0
