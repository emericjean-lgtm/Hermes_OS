"""Instantiates agents declared in config/agents.yaml.

Only entries with `enabled: true` are loaded — the rest of the roster
(Atlas, Aegis, Echo, ...) is declared for forward-compatibility but has no
implementation yet in the walking skeleton. Adding a real agent later is a
matter of writing backend/agents/<name>.py and flipping `enabled: true`,
not touching this loader.
"""
from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Optional

from backend.agents.base_agent import BaseAgent
from backend.connectors.ollama_client import OllamaClient, OllamaClientProtocol
from backend.core.config import get_settings, load_agents_config, load_models_config
from backend.core.router import ModelRouter


class AgentNotFoundError(KeyError):
    pass


class AgentRegistry:
    """Holds every enabled agent, uniformly constructed as
    agent_cls(ollama_client, router, models_config, cloud_client). Not all
    agents are chat agents (e.g. AegisAgent exposes evaluate(), not
    respond()) — callers are expected to know which contract the agent they
    asked for implements; this registry only handles lookup by key."""

    def __init__(self, ollama_client: OllamaClientProtocol, router: ModelRouter, models_config: dict,
                 cloud_client: Optional[Any] = None) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config
        # HOS-066C: an OpenRouterClient, shared by every agent the same way
        # ollama_client is — None (the default) when OPENROUTER_API_KEY
        # isn't configured, in which case every agent runs local-only,
        # unchanged from before this existed.
        self._cloud_client = cloud_client
        self._agents: dict[str, Any] = {}
        self._load_enabled_agents()

    def _load_enabled_agents(self) -> None:
        agents_config = load_agents_config()["agents"]
        for agent_key, spec in agents_config.items():
            if not spec.get("enabled", False):
                continue
            module = importlib.import_module(spec["module"])
            agent_cls = getattr(module, spec["class_name"])
            # Only BaseAgent subclasses accept cloud_client (HOS-066C) — a
            # few enabled agents (AegisAgent, KronosAgent, EchoAgent) predate
            # BaseAgent and keep their own 3-arg constructor; passing a 4th
            # positional arg to those would be a TypeError, not a no-op.
            if issubclass(agent_cls, BaseAgent):
                self._agents[agent_key] = agent_cls(
                    self._ollama, self._router, self._models_config, self._cloud_client,
                )
            else:
                self._agents[agent_key] = agent_cls(self._ollama, self._router, self._models_config)

    @property
    def ollama_client(self) -> OllamaClientProtocol:
        """The single OllamaClient every agent here shares — exposed so
        non-agent infrastructure (e.g. monitoring/gpu_monitor.py's loaded-
        models check) can reuse the same connection instead of opening a
        second one to the same Ollama server."""
        return self._ollama

    def get(self, agent_key: str) -> Any:
        try:
            return self._agents[agent_key]
        except KeyError as exc:
            raise AgentNotFoundError(
                f"Agent {agent_key!r} is not enabled or does not exist. "
                f"Enabled agents: {sorted(self._agents)}"
            ) from exc

    def list_enabled(self) -> list[str]:
        return sorted(self._agents)


def always_loaded_models(models_config: dict) -> set[str]:
    """Ollama tags for roles flagged `always_loaded: true` in
    config/models.yaml — pinned in VRAM rather than expiring on idle
    (§22). Returned as tags, not role names, because that's what the
    Ollama API keys on and what OllamaClient sees per request."""
    return {
        role["model"]
        for role in models_config.get("roles", {}).values()
        if role.get("always_loaded")
    }


@lru_cache
def get_agent_registry() -> AgentRegistry:
    from backend.connectors.openrouter_client import OpenRouterClient

    settings = get_settings()
    models_config = load_models_config()
    ollama_client = OllamaClient(
        settings.ollama_api_url,
        keep_alive=settings.ollama_keep_alive,
        always_loaded_models=always_loaded_models(models_config),
        default_num_ctx=settings.ollama_num_ctx,
    )
    router = ModelRouter(models_config)
    return AgentRegistry(ollama_client, router, models_config, OpenRouterClient.from_settings())
