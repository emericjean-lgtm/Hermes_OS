from __future__ import annotations

import pytest

from backend.agents.hermes_scribe import HermesScribeAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_write_builds_prompt_with_format_tone_and_context(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    scribe = HermesScribeAgent(fake_ollama_client, router, models_config)

    decision, stream = await scribe.write(
        "Write a short README section about the Echo agent.",
        format="markdown",
        tone="formal",
        context="Echo is the memory agent, built with SQLite + ChromaDB.",
    )
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    assert decision.task_type == "writing"

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "markdown format" in system_prompt
    assert "formal tone" in system_prompt
    assert "Echo is the memory agent, built with SQLite + ChromaDB." in system_prompt

    user_message = fake_ollama_client.last_chat_call["messages"][1]["content"]
    assert user_message == "Write a short README section about the Echo agent."


@pytest.mark.asyncio
async def test_write_without_context_omits_background_section(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    scribe = HermesScribeAgent(fake_ollama_client, router, models_config)

    _decision, stream = await scribe.write("Write a haiku about GPUs.")
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "Background context" not in system_prompt


@pytest.mark.asyncio
async def test_write_reuses_already_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    # the orchestrator model is a lower-priority candidate than standard
    # for "writing" — proves "already loaded" beats priority order.
    orchestrator_model = models_config["roles"]["orchestrator"]["model"]
    client = FakeOllamaClient(running_models=[orchestrator_model])
    router = ModelRouter(models_config)
    scribe = HermesScribeAgent(client, router, models_config)

    decision, _stream = await scribe.write("brief")

    assert decision.model == orchestrator_model
    assert "already loaded" in decision.reason
