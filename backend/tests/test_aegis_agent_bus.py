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
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ALLOWED_PATHS", str(tmp_path))
    get_settings.cache_clear()
    get_message_bus.cache_clear()
    monkeypatch.setattr("backend.agents.aegis.load_security_config", lambda: security_config)

    router = ModelRouter(models_config)
    agent = AegisAgent(fake_ollama_client, router, models_config)

    try:
        yield agent
    finally:
        get_settings.cache_clear()
        get_message_bus.cache_clear()


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
