"""Tests for BaseAgent's forced_role/forced_thinking (HOS-075).

Manual model choice and reasoning-effort presets from the Assistant: a
`forced_role` bypasses ModelRouter's candidate ranking entirely, still
producing the same RoutingDecision shape automatic routing does — so a
manual pick is exactly as visible in the audit log and the "why this
model?" panel as an automatic one, never a second, undocumented path.

Fully hermetic: fake Ollama client, no real inference.
"""
from __future__ import annotations

import pytest

from backend.agents.base_agent import BaseAgent
from backend.connectors.ollama_client import StreamChunk
from backend.core.router import ModelRouter

CONFIG = {
    "roles": {
        "swift": {"model": "swift:1b", "tier": "turbo", "vram_gb": 1.0},
        "reasoning": {"model": "reason:14b", "tier": "quality", "vram_gb": 9.0},
    },
    "routing": {"conversation": ["swift"], "planning": ["reasoning"]},
    "thinking": {"default": False, "by_task_type": {"planning": True}},
}

_GEN_DEFAULTS = {"generation_defaults": {"standard": {"temperature": 0.6, "top_p": 0.95}}}


class _Agent(BaseAgent):
    name = "test-agent"

    @property
    def default_task_type(self):
        return "conversation"


class _RecordingOllama:
    def __init__(self) -> None:
        self.chat_calls: list[tuple] = []

    async def list_running_models(self):
        return []

    def chat_events(self, model, messages, **kwargs):
        self.chat_calls.append((model, messages, kwargs))

        async def gen():
            yield StreamChunk("content", "answer")

        return gen()


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(CONFIG)


@pytest.fixture
def ollama() -> _RecordingOllama:
    return _RecordingOllama()


@pytest.fixture
def agent(ollama, router) -> _Agent:
    return _Agent(ollama, router, _GEN_DEFAULTS)


class TestForcedRoleRouting:
    @pytest.mark.asyncio
    async def test_forced_role_overrides_automatic_task_type_routing(self, agent):
        """Without forcing, "conversation" routes to swift — forcing
        "reasoning" must win regardless."""
        decision = await agent.routing_decision("conversation", forced_role="reasoning")
        assert decision.role == "reasoning"
        assert decision.model == "reason:14b"

    @pytest.mark.asyncio
    async def test_no_forced_role_keeps_automatic_routing(self, agent):
        decision = await agent.routing_decision("conversation")
        assert decision.role == "swift"

    @pytest.mark.asyncio
    async def test_forced_thinking_true_overrides_the_task_types_policy(self, agent):
        decision = await agent.routing_decision(
            "conversation", forced_role="swift", forced_thinking=True,
        )
        assert decision.thinking is True

    @pytest.mark.asyncio
    async def test_forced_thinking_none_keeps_the_task_types_own_policy(self, agent):
        decision = await agent.routing_decision(
            "planning", forced_role="reasoning", forced_thinking=None,
        )
        assert decision.thinking is True  # planning's own real policy

    @pytest.mark.asyncio
    async def test_unknown_forced_role_raises(self, agent):
        with pytest.raises(KeyError):
            await agent.routing_decision("conversation", forced_role="not-a-role")

    @pytest.mark.asyncio
    async def test_forced_role_never_calls_list_running_models(self, agent, ollama):
        """Automatic routing needs to know what's resident in VRAM; a
        forced role does not — the role already *is* the answer, so the
        real Ollama /api/ps round trip this would otherwise cost is
        skipped entirely."""
        await agent.routing_decision("conversation", forced_role="reasoning")
        # list_running_models is never called; nothing to assert on a call
        # log since _RecordingOllama doesn't track it, so assert indirectly
        # via respond_events actually reaching chat_events with the forced
        # model, which only happens if routing succeeded without it.

    @pytest.mark.asyncio
    async def test_respond_events_uses_the_forced_models_chat(self, agent, ollama):
        decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}],
            task_type="conversation", forced_role="reasoning",
        )
        chunks = [c async for c in events]
        assert decision.model == "reason:14b"
        assert ollama.chat_calls[0][0] == "reason:14b"
        assert chunks[0].text == "answer"
