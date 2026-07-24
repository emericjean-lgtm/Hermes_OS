from __future__ import annotations

import pytest

from backend.agents.minerva import MinervaAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_synthesize_includes_citations_and_sources(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    minerva = MinervaAgent(fake_ollama_client, router, models_config)

    passages = [
        {"id": "doc-0", "content": "Hermes Ollama runs on an RX 6800.", "metadata": {"source": "readme.md"}},
        {"id": "doc-1", "content": "The router picks models from models.yaml.", "metadata": {"source": "router.py"}},
    ]

    decision, stream = await minerva.synthesize("What GPU does Hermes Ollama use?", passages)
    tokens = [chunk async for chunk in stream]

    assert decision.task_type == "research"
    assert "".join(tokens) == "Hello, world!"  # fake client's canned response

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "[1] (source: readme.md)" in system_prompt
    assert "Hermes Ollama runs on an RX 6800." in system_prompt
    assert "[2] (source: router.py)" in system_prompt


@pytest.mark.asyncio
async def test_synthesize_with_no_passages_says_so(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    minerva = MinervaAgent(fake_ollama_client, router, models_config)

    _decision, stream = await minerva.synthesize("anything?", [])
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "No relevant passages were found." in system_prompt


@pytest.mark.asyncio
async def test_synthesize_reuses_already_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    # the orchestrator model is a lower-priority candidate than
    # standard for "research" — proves "already loaded" beats priority.
    orchestrator_model = models_config["roles"]["orchestrator"]["model"]
    client = FakeOllamaClient(running_models=[orchestrator_model])
    router = ModelRouter(models_config)
    minerva = MinervaAgent(client, router, models_config)

    decision, _stream = await minerva.synthesize("q", [])

    assert decision.model == orchestrator_model
    assert "already loaded" in decision.reason
