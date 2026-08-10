"""Hermes Swift — ultra-fast pre-routing classifier (cahier des charges
§9.1: "Demande -> type de tache + tier"), the one always-on agent besides
Aegis/Echo.

classify() asks the fast `swift` model (config/models.yaml's
"classification" task type -> role swift, qwen3.5:2b as of HOS-079, kept
loaded at all times) to label a raw request with one of the task types in models.yaml's
routing matrix — the same labels ModelRouter.select_model() already
understands, so the result can be fed straight back into routing.
parse_task_type() is a separate, pure string parser (no LLM/network
call): LLM output can't be trusted to always follow the one-word
instruction, so it falls back to a caller-supplied default rather than
raising or returning something ModelRouter would reject.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agents.base_agent import BaseAgent
from backend.core.router import RoutingDecision


class HermesSwiftAgent(BaseAgent):
    name = "hermes_swift"

    @property
    def default_task_type(self) -> str:
        return "classification"

    @property
    def known_task_types(self) -> list[str]:
        return sorted(self._models_config["routing"])

    async def classify(self, request: str) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Ask Swift to label `request` with one task type from
        models.yaml's routing matrix. Returns the routing decision plus
        the raw reply stream — join it and pass it through
        parse_task_type() to get a validated label."""
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": request},
        ]
        return await self.respond(messages, task_type=self.default_task_type)

    def _build_system_prompt(self) -> str:
        types = ", ".join(self.known_task_types)
        return (
            "You are Hermes Swift, an ultra-fast request classifier. Read "
            "the user's request and reply with EXACTLY ONE word: the task "
            "type that best matches it. Nothing else — no punctuation, no "
            "explanation.\n\n"
            f"Valid task types: {types}"
        )

    def parse_task_type(self, text: str, *, default: str = "conversation") -> str:
        """Extract a valid task type from Swift's reply, or `default` if
        the reply doesn't match one of models.yaml's routing keys exactly."""
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        candidate = first_line.strip().strip(".:,!").lower()
        return candidate if candidate in self.known_task_types else default
