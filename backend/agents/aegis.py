"""Aegis — the always-on security gate (cahier des charges §9.1, §17).

Aegis does not produce chat completions, so it deliberately does not
subclass BaseAgent: its contract is evaluate(ActionRequest) -> AegisDecision,
not respond(messages) -> streamed text. It still takes the same
(ollama_client, router, models_config) constructor as every other agent so
AgentRegistry can instantiate it uniformly from config/agents.yaml — the
LLM client/router are unused for now (see aegis_engine.py for why the
decision engine is deterministic, not model-based) but kept for the
future advisory pass on ambiguous cases.
"""
from __future__ import annotations

from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings, load_security_config
from backend.core.router import ModelRouter
from backend.security.aegis_engine import ActionRequest, AegisDecision, AegisEngine
from backend.security.permission_matrix import PermissionMatrix


class AegisAgent:
    name: ClassVar[str] = "aegis"

    def __init__(
        self,
        ollama_client: OllamaClientProtocol,
        router: ModelRouter,
        models_config: dict,
    ) -> None:
        self._ollama = ollama_client
        self._router = router
        self._models_config = models_config

        settings = get_settings()
        matrix = PermissionMatrix(load_security_config())
        self._engine = AegisEngine(matrix, settings.allowed_paths_list)

    def evaluate(self, action: ActionRequest) -> AegisDecision:
        return self._engine.evaluate(action)
