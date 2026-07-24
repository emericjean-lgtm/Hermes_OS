from __future__ import annotations

import pytest

from backend.agents.hermes_swift import HermesSwiftAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_classify_lists_known_task_types_in_prompt(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    swift = HermesSwiftAgent(fake_ollama_client, router, models_config)

    decision, stream = await swift.classify("Refactor this function to be async.")
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    assert decision.task_type == "classification"

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "code_refactor" in system_prompt
    assert "research" in system_prompt

    user_message = fake_ollama_client.last_chat_call["messages"][1]["content"]
    assert user_message == "Refactor this function to be async."


@pytest.mark.asyncio
async def test_classify_reuses_already_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    client = FakeOllamaClient(running_models=["qwen3:1.7b"])
    router = ModelRouter(models_config)
    swift = HermesSwiftAgent(client, router, models_config)

    decision, _stream = await swift.classify("anything")

    assert decision.model == "qwen3:1.7b"
    assert "already loaded" in decision.reason


def test_parse_task_type_valid_label(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    swift = HermesSwiftAgent(fake_ollama_client, router, models_config)

    assert swift.parse_task_type("code_generation") == "code_generation"


def test_parse_task_type_strips_punctuation_and_case(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    swift = HermesSwiftAgent(fake_ollama_client, router, models_config)

    assert swift.parse_task_type("Research.\n") == "research"


def test_parse_task_type_unknown_label_falls_back_to_default(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    swift = HermesSwiftAgent(fake_ollama_client, router, models_config)

    assert swift.parse_task_type("I'm not sure, maybe coding?") == "conversation"
    assert swift.parse_task_type("garbage", default="research") == "research"
