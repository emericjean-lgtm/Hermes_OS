from __future__ import annotations

import pytest

from backend.agents.aegis import AegisAgent
from backend.core.config import get_settings
from backend.core.message_bus import MessageType, get_message_bus
from backend.core.router import ModelRouter
from backend.security.aegis_engine import ActionRequest, Verdict

# AegisAgent.evaluate() publishes to the message bus around every call
# (see agents/aegis.py) — these tests exercise that wiring specifically.
# test_aegis.py covers AegisEngine's own decision logic in isolation, with
# no bus involved at all.


@pytest.fixture
def aegis_agent(monkeypatch, fake_ollama_client, models_config, security_config, tmp_path):
    from backend.projects.store import get_project_store

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    get_project_store.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    router = ModelRouter(models_config)
    agent = AegisAgent(fake_ollama_client, router, models_config)

    try:
        yield agent
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()
        get_project_store.cache_clear()


def _by_type(messages) -> dict:
    return {m.type: m for m in messages}


def test_evaluate_publishes_request_and_granted_on_allow(aegis_agent, tmp_path):
    target = str(tmp_path / "f.txt")

    decision = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="read it",
            target_path=target,
            requesting_agent="test-agent",
            task_id="task-1",
        )
    )

    assert decision.verdict is Verdict.ALLOW

    messages = get_message_bus().list_messages(task_id="task-1")
    assert len(messages) == 2
    by_type = _by_type(messages)

    request_msg = by_type[MessageType.VALIDATION_REQUEST.value]
    assert request_msg.from_agent == "test-agent"
    assert request_msg.to_agent == "aegis"
    assert request_msg.payload["action_type"] == "file_read"

    granted_msg = by_type[MessageType.VALIDATION_GRANTED.value]
    assert granted_msg.from_agent == "aegis"
    assert granted_msg.to_agent == "test-agent"
    assert granted_msg.payload["verdict"] == "allow"


def test_evaluate_publishes_denied_on_deny(aegis_agent, tmp_path):
    outside = str(tmp_path.parent / "elsewhere" / "f.txt")

    decision = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="read it",
            target_path=outside,
            requesting_agent="test-agent",
            task_id="task-2",
        )
    )

    assert decision.verdict is Verdict.DENY

    by_type = _by_type(get_message_bus().list_messages(task_id="task-2"))
    assert MessageType.VALIDATION_DENIED.value in by_type
    assert by_type[MessageType.VALIDATION_DENIED.value].payload["verdict"] == "deny"


def test_evaluate_publishes_escalation_on_require_human_validation(aegis_agent):
    decision = aegis_agent.evaluate(
        ActionRequest(
            action_type="git_critical",
            description="force push to main",
            requesting_agent="test-agent",
            task_id="task-3",
        )
    )

    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION

    by_type = _by_type(get_message_bus().list_messages(task_id="task-3"))
    assert MessageType.ESCALATION.value in by_type
    assert by_type[MessageType.ESCALATION.value].from_agent == "aegis"
    assert by_type[MessageType.ESCALATION.value].to_agent == "test-agent"


def test_evaluate_defaults_requesting_agent_to_unknown(aegis_agent):
    aegis_agent.evaluate(ActionRequest(action_type="git_critical", description="?"))

    messages = get_message_bus().list_messages(agent="unknown")
    assert len(messages) == 2


def test_evaluate_publishes_with_project_id(aegis_agent):
    aegis_agent.evaluate(
        ActionRequest(
            action_type="git_critical",
            description="?",
            requesting_agent="test-agent",
            project_id="proj-1",
        )
    )

    messages = get_message_bus().list_messages(project_id="proj-1")
    assert len(messages) == 2
    assert all(m.project_id == "proj-1" for m in messages)


def test_evaluate_narrows_to_project_root_when_project_has_one(aegis_agent, tmp_path):
    from backend.projects.store import get_project_store

    project_dir = tmp_path / "project-a"
    project_dir.mkdir()
    other_dir = tmp_path / "project-b"
    other_dir.mkdir()
    project = get_project_store().create(name="A", root_path=str(project_dir))

    inside = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="?",
            target_path=str(project_dir / "f.txt"),
            project_id=project.id,
        )
    )
    assert inside.verdict is Verdict.ALLOW

    outside = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="?",
            target_path=str(other_dir / "f.txt"),
            project_id=project.id,
        )
    )
    assert outside.verdict is Verdict.DENY


def test_evaluate_falls_back_to_global_whitelist_when_project_has_no_root_path(
    aegis_agent, tmp_path
):
    from backend.projects.store import get_project_store

    project = get_project_store().create(name="No root")

    decision = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="?",
            target_path=str(tmp_path / "f.txt"),
            project_id=project.id,
        )
    )

    assert decision.verdict is Verdict.ALLOW


def test_evaluate_requires_human_validation_for_unknown_project_id(aegis_agent, tmp_path):
    decision = aegis_agent.evaluate(
        ActionRequest(
            action_type="file_read",
            description="?",
            target_path=str(tmp_path / "f.txt"),
            project_id="does-not-exist",
        )
    )

    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION


@pytest.mark.asyncio
async def test_advise_is_noop_on_allow(aegis_agent, tmp_path):
    decision = aegis_agent.evaluate(
        ActionRequest(action_type="file_read", description="?", target_path=str(tmp_path / "f.txt"))
    )
    assert decision.verdict is Verdict.ALLOW

    advised = await aegis_agent.advise(
        ActionRequest(action_type="file_read", description="?", target_path=str(tmp_path / "f.txt")),
        decision,
    )
    assert advised is decision
    assert advised.advisory is None


@pytest.mark.asyncio
async def test_advise_is_noop_on_deny(aegis_agent, tmp_path):
    outside = str(tmp_path.parent / "elsewhere" / "f.txt")
    action = ActionRequest(action_type="file_read", description="?", target_path=outside)
    decision = aegis_agent.evaluate(action)
    assert decision.verdict is Verdict.DENY

    advised = await aegis_agent.advise(action, decision)
    assert advised is decision
    assert advised.advisory is None


@pytest.mark.asyncio
async def test_advise_calls_llm_on_require_human_validation(aegis_agent, fake_ollama_client, models_config):
    action = ActionRequest(action_type="git_critical", description="force push to main")
    decision = aegis_agent.evaluate(action)
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION

    advised = await aegis_agent.advise(action, decision)

    assert advised.advisory is not None
    assert advised.verdict is Verdict.REQUIRE_HUMAN_VALIDATION  # unchanged
    assert advised.reason == decision.reason  # unchanged

    security_model = models_config["roles"]["security"]["model"]
    assert fake_ollama_client.last_chat_call["model"] == security_model
    assert "force push to main" in fake_ollama_client.last_chat_call["messages"][1]["content"]
    # think=True is still sent as harmless defense-in-depth, but the
    # actual leak protection is _extract_advisory()'s marker parsing —
    # see the tests below and agents/aegis.py's module docstring for why
    # think=True alone is confirmed NOT to work for phi4-reasoning on
    # real Ollama 0.32.0.
    assert fake_ollama_client.last_chat_call["think"] is True


@pytest.mark.asyncio
async def test_advise_strips_reasoning_preamble_before_marker(security_config, models_config, tmp_path, monkeypatch):
    from backend.tests.conftest import FakeOllamaClient

    reasoning_client = FakeOllamaClient(
        response_chunks=[
            "We need to figure out ", "whether this is risky. ",
            "Let me think step by step...\n",
            "ADVISORY: ", "Double-check the target branch before approving.",
        ]
    )
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)
    router = ModelRouter(models_config)
    agent = AegisAgent(reasoning_client, router, models_config)

    action = ActionRequest(action_type="git_critical", description="force push to main")
    decision = agent.evaluate(action)
    assert decision.verdict is Verdict.REQUIRE_HUMAN_VALIDATION

    advised = await agent.advise(action, decision)

    assert advised.advisory == "Double-check the target branch before approving."
    assert "step by step" not in advised.advisory


@pytest.mark.asyncio
async def test_advise_falls_back_to_raw_text_without_marker(aegis_agent, fake_ollama_client):
    # aegis_agent's fake_ollama_client fixture defaults to chunks that
    # never include "ADVISORY:" — degrade-gracefully behavior (same
    # philosophy as VeritasAgent.parse_verdict()): a human reviewer still
    # gets the model's raw text rather than an empty advisory.
    action = ActionRequest(action_type="git_critical", description="force push to main")
    decision = aegis_agent.evaluate(action)

    advised = await aegis_agent.advise(action, decision)

    assert advised.advisory == "Hello, world!"
