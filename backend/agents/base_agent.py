"""Abstract base class every Hermes agent implements.

An agent does not own a fixed model — it asks the ModelRouter for the best
model given a task_type, so the economy-of-VRAM principle (§7, principle 10
of the cahier des charges) is enforced centrally rather than per agent.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.router import ModelRouter, RoutingDecision


class BaseAgent(ABC):
    name: ClassVar[str]

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
    ) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config

    @property
    @abstractmethod
    def default_task_type(self) -> str:
        """Task type used to look up a model in the routing matrix when the
        caller doesn't specify one explicitly."""

    async def routing_decision(self, task_type: str | None = None) -> RoutingDecision:
        running = await self._ollama.list_running_models()
        loaded_tags = self._router.running_model_tags(running)
        return self._router.select_model(
            task_type or self.default_task_type,
            loaded_models=loaded_tags,
        )

    def generation_params(self, sensitivity: str = "standard") -> dict:
        return self._models_config["generation_defaults"][sensitivity]

    async def respond(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str | None = None,
        sensitivity: str = "standard",
    ) -> tuple[RoutingDecision, AsyncIterator[str]]:
        """Resolve a model via the router, then return the routing decision
        alongside the streamed response so callers can log/display both."""
        decision = await self.routing_decision(task_type)
        params = self.generation_params(sensitivity)
        stream = self._ollama.chat_stream(
            decision.model,
            messages,
            temperature=params["temperature"],
            top_p=params["top_p"],
            # From the routing decision, not resolved here: the value is
            # per task_type (config/models.yaml → `thinking`) and must be
            # the same one the audit log records. See §22.1 — reasoning
            # costs ~3.5 s of silence before the first visible word.
            think=decision.thinking,
        )
        return decision, stream
