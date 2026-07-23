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

from backend.agents.base_agent import BaseAgent
from backend.connectors.ollama_client import OllamaClient, OllamaClientProtocol
from backend.core.config import get_settings, load_agents_config, load_models_config
from backend.core.router import ModelRouter


class AgentNotFoundError(KeyError):
    pass


class AgentRegistry:
    def __init__(self, ollama_client: OllamaClientProtocol, router: ModelRouter, models_config: dict) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config
        self._agents: dict[str, BaseAgent] = {}
        self._load_enabled_agents()

    def _load_enabled_agents(self) -> None:
        agents_config = load_agents_config()["agents"]
        for agent_key, spec in agents_config.items():
            if not spec.get("enabled", False):
                continue
            module = importlib.import_module(spec["module"])
            agent_cls = getattr(module, spec["class_name"])
            self._agents[agent_key] = agent_cls(self._ollama, self._router, self._models_config)

    def get(self, agent_key: str) -> BaseAgent:
        try:
            return self._agents[agent_key]
        except KeyError as exc:
            raise AgentNotFoundError(
                f"Agent {agent_key!r} is not enabled or does not exist. "
                f"Enabled agents: {sorted(self._agents)}"
            ) from exc

    def list_enabled(self) -> list[str]:
        return sorted(self._agents)


@lru_cache
def get_agent_registry() -> AgentRegistry:
    settings = get_settings()
    ollama_client = OllamaClient(settings.ollama_api_url, keep_alive=settings.ollama_keep_alive)
    router = ModelRouter(load_models_config())
    return AgentRegistry(ollama_client, router, load_models_config())
