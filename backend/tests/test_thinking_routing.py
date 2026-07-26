"""§22.1 — reasoning is enabled per task type, and the choice is visible.

Measured on RX 6800 with qwen3.5:9b, model warm: 4 223 ms to the first
*content* token with reasoning, 675 ms without. The first token of any
kind arrives in ~660 ms either way — the gap is the reasoning phase,
which chat_stream does not yield, so the user sees nothing for ~3.5 s.
Tier 2's budget is 3 s, which is why T3 was failing.
"""
from __future__ import annotations

import pytest

from backend.connectors.ollama_client import StreamChunk
from backend.core.router import ModelRouter

CONFIG = {
    "roles": {
        "small": {"model": "small:1b", "tier": "turbo", "vram_gb": 1.0},
        "big": {"model": "big:30b", "tier": "quality", "vram_gb": 20.0},
    },
    "routing": {"conversation": ["small"], "planning": ["big", "small"]},
    "thinking": {"default": False, "by_task_type": {"planning": True}},
}


def test_reasoning_is_on_where_it_changes_the_answer():
    assert ModelRouter(CONFIG).select_model("planning").thinking is True


def test_reasoning_is_off_where_it_only_adds_silence():
    assert ModelRouter(CONFIG).select_model("conversation").thinking is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"loaded_models": ["big:30b"]},          # path 1: already loaded
        {"available_vram_gb": 40.0},             # path 2: fits VRAM
        {"available_vram_gb": 0.5},              # path 3: nothing fits, downgrade
        {},                                      # path 4: no VRAM info
    ],
)
def test_every_routing_path_carries_the_decision(kwargs):
    """select_model has four exit paths. Setting `thinking` on three of
    them would ship a field that is right only sometimes — the same shape
    of bug as the audit log's silently-null first_token_ms."""
    assert ModelRouter(CONFIG).select_model("planning", **kwargs).thinking is True


def test_an_unlisted_task_type_takes_the_default():
    config = {**CONFIG, "routing": {**CONFIG["routing"], "nouveau": ["small"]}}

    assert ModelRouter(config).select_model("nouveau").thinking is False


def test_the_real_config_keeps_reasoning_where_it_matters():
    """Pins the actual shipped config, not a fixture — a regression here
    silently degrades every code and planning task."""
    router = ModelRouter()

    for task_type in ("reasoning", "verification", "planning",
                      "code_analysis", "code_generation", "code_refactor"):
        assert router.thinking_for(task_type) is True, task_type
    for task_type in ("conversation", "classification", "extraction",
                      "summary_short", "rephrase"):
        assert router.thinking_for(task_type) is False, task_type


def test_a_config_without_a_thinking_block_still_works():
    """models.yaml predates this feature; an older copy must not crash."""
    bare = {k: v for k, v in CONFIG.items() if k != "thinking"}

    assert ModelRouter(bare).select_model("planning").thinking is False


@pytest.mark.asyncio
async def test_the_decision_actually_reaches_ollama():
    """The load-bearing test. Everything above is decorative if the flag
    stops at the router and never lands in the request payload."""
    from backend.agents.base_agent import BaseAgent

    sent = {}

    class FakeOllama:
        async def list_running_models(self):
            return []

        def chat_events(self, model, messages, **kwargs):
            sent.update(kwargs)

            async def empty():
                return
                yield  # pragma: no cover

            return empty()

    class Planner(BaseAgent):
        name = "planner"

        @property
        def default_task_type(self):
            return "planning"

    agent = Planner(FakeOllama(), ModelRouter(CONFIG),
                    {"generation_defaults": {"standard": {"temperature": 0.6, "top_p": 0.95}}})
    await agent.respond([{"role": "user", "content": "x"}])

    assert sent["think"] is True

    await agent.respond([{"role": "user", "content": "x"}], task_type="conversation")
    assert sent["think"] is False
