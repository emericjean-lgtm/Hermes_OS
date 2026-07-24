from __future__ import annotations

import pytest

from backend.agents.veritas import VeritasAgent
from backend.core.router import ModelRouter


@pytest.mark.asyncio
async def test_review_builds_prompt_with_context_and_criteria(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    veritas = VeritasAgent(fake_ollama_client, router, models_config)

    decision, stream = await veritas.review(
        "def add(a, b): return a - b",
        context="Implement an addition function.",
        criteria=["matches the function name's intent", "has a test"],
    )
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    assert decision.task_type == "verification"

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "Implement an addition function." in system_prompt
    assert "matches the function name's intent" in system_prompt
    assert "has a test" in system_prompt

    user_message = fake_ollama_client.last_chat_call["messages"][1]["content"]
    assert user_message == "def add(a, b): return a - b"


@pytest.mark.asyncio
async def test_review_with_no_criteria_uses_default(fake_ollama_client, models_config):
    router = ModelRouter(models_config)
    veritas = VeritasAgent(fake_ollama_client, router, models_config)

    _decision, stream = await veritas.review("some output")
    [_chunk async for _chunk in stream]  # chat_stream is a lazy async generator

    system_prompt = fake_ollama_client.last_chat_call["messages"][0]["content"]
    assert "general correctness and completeness" in system_prompt


@pytest.mark.asyncio
async def test_review_reuses_already_loaded_model(models_config):
    from backend.tests.conftest import FakeOllamaClient

    # reasoning is the priority-1 candidate for "verification" already, so
    # use a lower-priority candidate (security) to prove "already loaded"
    # beats priority order.
    security_model = models_config["roles"]["security"]["model"]
    client = FakeOllamaClient(running_models=[security_model])
    router = ModelRouter(models_config)
    veritas = VeritasAgent(client, router, models_config)

    decision, _stream = await veritas.review("output")

    assert decision.model == security_model
    assert "already loaded" in decision.reason


def test_parse_verdict_well_formed_reply():
    reply = (
        "VERDICT: needs_revision\n"
        "ISSUES:\n"
        "- off-by-one error in the loop bound\n"
        "- missing docstring\n"
        "CORRECTIONS:\n"
        "Change range(n) to range(n + 1) and add a one-line docstring."
    )

    parsed = VeritasAgent.parse_verdict(reply)

    assert parsed["verdict"] == "needs_revision"
    assert parsed["issues"] == [
        "off-by-one error in the loop bound",
        "missing docstring",
    ]
    assert parsed["corrections"] == "Change range(n) to range(n + 1) and add a one-line docstring."
    assert parsed["raw"] == reply


def test_parse_verdict_approved_with_no_issues():
    reply = "VERDICT: approved\nISSUES:\n- none\nCORRECTIONS:\nnone"

    parsed = VeritasAgent.parse_verdict(reply)

    assert parsed["verdict"] == "approved"
    assert parsed["issues"] == []
    assert parsed["corrections"] == ""


def test_parse_verdict_malformed_reply_falls_back_to_unknown():
    reply = "Looks fine to me, ship it."

    parsed = VeritasAgent.parse_verdict(reply)

    assert parsed["verdict"] == "unknown"
    assert parsed["issues"] == []
    assert parsed["raw"] == reply
