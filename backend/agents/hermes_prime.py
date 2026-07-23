"""Hermes Prime — the orchestrator agent.

In the walking skeleton, Prime is the sole entry point for /chat: it takes
the raw conversation, resolves the best model for a plain "conversation"
task via the router, and streams the response back. Delegation to other
agents (Atlas, Minerva, ...) is added once those agents exist (§9).
"""
from __future__ import annotations

from backend.agents.base_agent import BaseAgent


class HermesPrimeAgent(BaseAgent):
    name = "hermes_prime"

    @property
    def default_task_type(self) -> str:
        return "conversation"
