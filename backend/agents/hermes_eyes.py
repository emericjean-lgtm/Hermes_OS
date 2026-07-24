"""Hermes Eyes — vision agent (cahier des charges §9.1: "Image ->
description/extraction").

analyze() is the same thin-wrapper pattern as Minerva.synthesize(),
Veritas.review(), and HermesScribeAgent.write(): prompt construction +
BaseAgent.respond(), no extra logic. The one difference is the images
themselves travel on the user message's `images` field (a list of
base64-encoded strings, Ollama's own multimodal format, no data URI
prefix) — this is why BaseAgent.respond()'s message type was widened
from dict[str, str] to dict[str, Any].
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agents.base_agent import BaseAgent
from backend.core.router import RoutingDecision

DEFAULT_ANALYSIS_PROMPT = (
    "Describe this image in detail and extract any text or notable data it contains."
)


class HermesEyesAgent(BaseAgent):
    name = "hermes_eyes"

    @property
    def default_task_type(self) -> str:
        return "vision"

    async def analyze(
        self,
        images: list[str],
        *,
        prompt: str = DEFAULT_ANALYSIS_PROMPT,
        context: str = "",
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Analyze one or more images. `images` are base64-encoded strings
        (no data URI prefix). `prompt` is what to look for/describe,
        `context` is background the model should know (e.g. what the
        screenshot is from)."""
        if not images:
            raise ValueError("analyze() requires at least one image")

        messages = [
            {"role": "system", "content": self._build_system_prompt(context)},
            {"role": "user", "content": prompt, "images": images},
        ]
        return await self.respond(messages, task_type=self.default_task_type)

    @staticmethod
    def _build_system_prompt(context: str) -> str:
        prompt = (
            "You are Hermes Eyes, a vision analysis agent. Look carefully at "
            "the attached image(s) and answer precisely, quoting any text you "
            "can read verbatim rather than paraphrasing it."
        )
        if context:
            prompt += f"\n\nBackground context:\n{context}"
        return prompt
