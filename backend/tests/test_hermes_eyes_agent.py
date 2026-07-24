from __future__ import annotations

import pytest

from backend.agents.hermes_eyes import HermesEyesAgent
from backend.core.router import ModelRouter

_FAKE_IMAGE = "aGVsbG8="  # base64 for "hello", content doesn't matter here


@pytest.mark.asyncio
async def test_analyze_attaches_images_to_user_message(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    eyes = HermesEyesAgent(fake_ollama_client, router, models_config)

    decision, stream = await eyes.analyze(
        [_FAKE_IMAGE], prompt="What GPU is shown in this screenshot?", context="A Task Manager screenshot."
    )
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    assert decision.task_type == "vision"

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "A Task Manager screenshot." in system_prompt

    user_message = fake_ollama_client.last_chat_call["messages"][1]
    assert user_message["content"] == "What GPU is shown in this screenshot?"
    assert user_message["images"] == [_FAKE_IMAGE]


@pytest.mark.asyncio
async def test_analyze_uses_default_prompt_and_no_context_section(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    eyes = HermesEyesAgent(fake_ollama_client, router, models_config)

    _decision, stream = await eyes.analyze([_FAKE_IMAGE])
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "Background context" not in system_prompt

    user_message = fake_ollama_client.last_chat_call["messages"][1]
    assert "Describe this image in detail" in user_message["content"]


@pytest.mark.asyncio
async def test_analyze_with_no_images_raises(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    eyes = HermesEyesAgent(fake_ollama_client, router, models_config)

    with pytest.raises(ValueError):
        await eyes.analyze([])


@pytest.mark.asyncio
async def test_analyze_reuses_already_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    client = FakeOllamaClient(running_models=["gemma4:12b"])
    router = ModelRouter(models_config)
    eyes = HermesEyesAgent(client, router, models_config)

    decision, _stream = await eyes.analyze([_FAKE_IMAGE])

    assert decision.model == "gemma4:12b"
    assert "already loaded" in decision.reason
