from __future__ import annotations

import pytest

from backend.agents.hermes_prime import HermesPrimeAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_prime_agent_streams_full_response(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    agent = HermesPrimeAgent(fake_ollama_client, router, models_config)

    decision, stream = await agent.respond([{"role": "user", "content": "hello"}])

    assert decision.task_type == "conversation"
    tokens = [chunk async for chunk in stream]
    assert "".join(tokens) == "Hello, world!"
    assert fake_ollama_client.last_chat_call["model"] == decision.model


@pytest.mark.asyncio
async def test_prime_agent_reuses_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    client = FakeOllamaClient(running_models=["deepseek-r1:14b"])
    router = ModelRouter(models_config)
    agent = HermesPrimeAgent(client, router, models_config)

    decision, _stream = await agent.respond(
        [{"role": "user", "content": "explain this bug"}],
        task_type="reasoning",
    )

    assert decision.model == "deepseek-r1:14b"
    assert "already loaded" in decision.reason
