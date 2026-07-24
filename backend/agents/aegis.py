"""Aegis — the always-on security gate (cahier des charges §9.1, §17).

Aegis does not produce chat completions, so it deliberately does not
subclass BaseAgent: its contract is evaluate(ActionRequest) -> AegisDecision,
not respond(messages) -> streamed text. It still takes the same
(ollama_client, router, models_config) constructor as every other agent so
AgentRegistry can instantiate it uniformly from config/agents.yaml — the
LLM client/router are unused for now (see aegis_engine.py for why the
decision engine is deterministic, not model-based) but kept for the
future advisory pass on ambiguous cases.

evaluate() also publishes to the message bus (core/message_bus.py,
§9.2/§24.4): a VALIDATION_REQUEST from the requesting agent, then a
VALIDATION_GRANTED/VALIDATION_DENIED/ESCALATION from Aegis, in every case
regardless of caller (this HTTP route, an MCP tool, or file_tools.py
called directly from Atlas) — the point of routing this through the bus
here rather than in each caller is that every evaluate() call gets traced
uniformly. ESCALATION covers require_human_validation: §9.2 defines it as
"agent -> user", and a human-validation verdict is exactly that request,
just raised by Aegis on the requesting agent's behalf rather than the
agent asking directly. Reached via the module-level get_message_bus()
singleton rather than constructor injection, the same pattern
MinervaAgent uses to reach Echo (see agents/minerva.py) — it keeps
AgentRegistry's uniform (ollama_client, router, models_config)
construction contract unchanged.
"""
from __future__ import annotations

from typing import ClassVar

from backend.connectors.ollama_client import OllamaClientProtocol
from backend.core.config import get_settings, load_security_config
from backend.core.message_bus import MessageType, get_message_bus
from backend.core.router import ModelRouter
from backend.security.aegis_engine import ActionRequest, AegisDecision, AegisEngine, Verdict
from backend.security.permission_matrix import PermissionMatrix

_VERDICT_MESSAGE_TYPE = {
    Verdict.ALLOW: MessageType.VALIDATION_GRANTED,
    Verdict.DENY: MessageType.VALIDATION_DENIED,
    Verdict.REQUIRE_HUMAN_VALIDATION: MessageType.ESCALATION,
}


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
        bus = get_message_bus()
        bus.publish(
            from_agent=action.requesting_agent,
            to_agent=self.name,
            type_=MessageType.VALIDATION_REQUEST,
            payload={
                "action_type": action.action_type,
                "description": action.description,
                "target_path": action.target_path,
            },
            task_id=action.task_id,
            project_id=action.project_id,
        )

        decision = self._engine.evaluate(action)

        bus.publish(
            from_agent=self.name,
            to_agent=action.requesting_agent,
            type_=_VERDICT_MESSAGE_TYPE[decision.verdict],
            payload={
                "verdict": decision.verdict.value,
                "reason": decision.reason,
                "action_type": decision.action_type,
            },
            task_id=action.task_id,
            project_id=action.project_id,
        )

        return decision
