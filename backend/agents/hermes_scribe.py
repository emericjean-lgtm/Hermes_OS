"""Hermes Scribe — writing & documentation agent (cahier des charges
§9.1: "Brief -> document").

write() is pure prompt-construction + chat completion (inherited from
BaseAgent.respond()), same pattern as Minerva.synthesize() and
Veritas.review() — no business logic beyond assembling the brief into a
system prompt, so it's fully testable with a fake Ollama client.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agents.base_agent import BaseAgent
from backend.core.router import RoutingDecision


class HermesScribeAgent(BaseAgent):
    name = "hermes_scribe"

    @property
    def default_task_type(self) -> str:
        return "writing"

    async def write(
        self,
        brief: str,
        *,
        format: str = "markdown",
        tone: str = "neutral",
        context: str = "",
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Turn a brief into a document. `format` is the output format
        (markdown, plain text, etc.), `tone` the writing register (neutral,
        formal, casual...), `context` any background the writer should
        know about but that isn't part of the brief itself (e.g. prior
        related documents, target audience)."""
        messages = [
            {"role": "system", "content": self._build_system_prompt(format, tone, context)},
            {"role": "user", "content": brief},
        ]
        return await self.respond(messages, task_type=self.default_task_type)

    @staticmethod
    def _build_system_prompt(format: str, tone: str, context: str) -> str:
        prompt = (
            "You are Hermes Scribe, a writing agent. Turn the user's brief "
            f"into a complete, well-structured document in {format} format, "
            f"written in a {tone} tone. Write only the document itself — no "
            "preamble, no meta-commentary about what you're about to write."
        )
        if context:
            prompt += f"\n\nBackground context:\n{context}"
        return prompt
