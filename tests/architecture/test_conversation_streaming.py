"""Tests for HOS-074 — streaming Assistant, conversation memory, lock scope.

Three real defects the Assistant audit found, all covered here:

* The chat had **no memory**: ``ResponseGenerator._ask_model`` only ever sent
  ``[system, user]`` to the model. Prior turns were stored in the session and
  never transmitted, so every message was answered as if it were the first
  ("quel est mon chiffre préféré ?" had nothing to refer back to).
* ``handle_message`` held the manager's lock across the whole inference
  (30–120 s on a local model), serialising every session operation
  app-wide — the same defect HOS-069 fixed in ``ExecutionController``.
* Nothing streamed: the Cockpit blocked on a single POST until the entire
  answer existed.

Fully hermetic: no Ollama, no HTTP server — the manager is driven directly.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from backend.conversation.conversation_manager import ConversationManager
from backend.conversation.conversation_models import (
    ConversationStatus,
    Message,
    MessageRole,
)


class TestConversationMemory:
    def test_history_is_sent_to_the_model(self):
        """The bug: prior turns never reached the model."""
        mgr = ConversationManager()
        session = mgr.create_session()
        _, messages, _ = mgr.begin_stream(session.session_id, "Mon chiffre préféré est 42")
        mgr.finish_stream(session.session_id, "Entendu.")
        _, messages, _ = mgr.begin_stream(session.session_id, "Quel est mon chiffre préféré ?")

        contents = [m["content"] for m in messages]
        assert any("42" in c for c in contents), (
            "the earlier turn must travel with the new message"
        )
        assert any("Entendu." in c for c in contents), (
            "Hermes's own prior answer is part of the conversation too"
        )

    def test_roles_are_mapped_to_the_api_shape(self):
        """Hermes's internal `hermes`/`agent` roles are not roles any
        OpenAI/Ollama-shaped API accepts — they must become `assistant`."""
        mgr = ConversationManager()
        session = mgr.create_session()
        session.messages.append(Message(role=MessageRole.USER, content="salut"))
        session.messages.append(Message(role=MessageRole.HERMES, content="bonjour"))
        session.messages.append(Message(role=MessageRole.AGENT, content="note d'agent"))

        messages = mgr.build_model_messages(session)

        assert messages[0]["role"] == "system"
        assert {m["role"] for m in messages} <= {"system", "user", "assistant"}
        assert [m["role"] for m in messages[1:]] == ["user", "assistant", "assistant"]

    def test_history_is_bounded(self):
        """A long session must not grow the prompt without limit."""
        mgr = ConversationManager()
        session = mgr.create_session()
        for i in range(60):
            session.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        messages = mgr.build_model_messages(session)

        # system prompt + at most MAX_HISTORY_MESSAGES turns
        assert len(messages) <= mgr.MAX_HISTORY_MESSAGES + 1
        assert messages[-1]["content"] == "m59"  # the most recent, not the oldest

    def test_empty_messages_are_not_sent(self):
        mgr = ConversationManager()
        session = mgr.create_session()
        session.messages.append(Message(role=MessageRole.HERMES, content="   "))
        session.messages.append(Message(role=MessageRole.USER, content="vrai message"))

        messages = mgr.build_model_messages(session)

        assert all(m["content"].strip() for m in messages)

    def test_system_prompt_carries_real_state(self):
        mgr = ConversationManager()
        session = mgr.create_session()
        session.context.active_mission_id = "mission-42"
        session.context.current_model = "qwen3.5:9b"

        messages = mgr.build_model_messages(session)

        assert messages[0]["role"] == "system"
        assert "mission-42" in messages[0]["content"]
        assert "qwen3.5:9b" in messages[0]["content"]


class TestStreamLifecycle:
    def test_begin_records_the_user_message_and_analyses_intent(self):
        mgr = ConversationManager()
        session = mgr.create_session()

        session_id, messages, intent = mgr.begin_stream(session.session_id, "bonjour")

        assert session_id == session.session_id
        assert session.messages[-1].content == "bonjour"
        assert session.messages[-1].role == MessageRole.USER
        assert intent.intent.value  # a real analysed intent, not a placeholder
        assert messages[-1] == {"role": "user", "content": "bonjour"}

    def test_unknown_session_opens_a_new_one(self):
        mgr = ConversationManager()
        session_id, _, _ = mgr.begin_stream("does-not-exist", "bonjour")
        assert mgr.get_session(session_id) is not None

    def test_finish_persists_the_answer(self):
        mgr = ConversationManager()
        session = mgr.create_session()
        mgr.begin_stream(session.session_id, "question")

        mgr.finish_stream(session.session_id, "réponse", metadata={"model": "qwen3:4b"})

        assert session.messages[-1].role == MessageRole.HERMES
        assert session.messages[-1].content == "réponse"
        assert session.messages[-1].metadata["model"] == "qwen3:4b"
        assert session.status == ConversationStatus.ACTIVE

    def test_interrupted_answer_is_kept(self):
        """A stopped generation produced real text; dropping it would
        desynchronise the next turn's history from what the user saw."""
        mgr = ConversationManager()
        session = mgr.create_session()
        mgr.begin_stream(session.session_id, "question")

        mgr.finish_stream(session.session_id, "début de réponse")

        assert session.messages[-1].content == "début de réponse"

    def test_empty_answer_adds_no_message(self):
        mgr = ConversationManager()
        session = mgr.create_session()
        mgr.begin_stream(session.session_id, "question")
        before = len(session.messages)

        mgr.finish_stream(session.session_id, "   ")

        assert len(session.messages) == before

    def test_finish_on_unknown_session_never_raises(self):
        ConversationManager().finish_stream("nope", "texte")  # must not raise


class TestLockIsNotHeldAcrossInference:
    def test_other_sessions_are_not_blocked_during_a_generation(self):
        """The real-world symptom: one user's 60 s answer froze every other
        conversation operation. begin/finish are split precisely so the
        inference happens between them, outside the lock."""
        mgr = ConversationManager()
        session = mgr.create_session()
        mgr.begin_stream(session.session_id, "question longue")

        # Simulates the window where inference runs — the manager must stay
        # usable throughout it.
        done: list[float] = []

        def other_work() -> None:
            start = time.monotonic()
            mgr.create_session()
            mgr.list_sessions()
            mgr.get_session(session.session_id)
            done.append(time.monotonic() - start)

        thread = threading.Thread(target=other_work)
        thread.start()
        thread.join(timeout=5)

        assert not thread.is_alive(), "manager was blocked during inference"
        assert done and done[0] < 1.0


# ── Route-level: forced_role / thinking / context (HOS-075) ─────────────

from backend.connectors.ollama_client import StreamChunk  # noqa: E402
from backend.core.router import ModelRouter  # noqa: E402


class _FakeAgent:
    """Mimics BaseAgent.respond_events' real contract without a real
    Ollama call — the route only needs a (decision, events) pair."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    async def respond_events(self, messages, *, task_type=None,
                              forced_role=None, forced_thinking=None):
        decision = self._router.decision_for_role(
            forced_role or "swift", task_type or "conversation", thinking=forced_thinking,
        )

        async def gen():
            yield StreamChunk("content", "réponse")

        return decision, gen()


class _FakeRegistry:
    def __init__(self, agent: _FakeAgent) -> None:
        self._agent = agent

    def get(self, name):
        return self._agent


_ROUTER_CONFIG = {
    "roles": {
        "swift": {"model": "swift:1b", "tier": "turbo", "vram_gb": 1.0, "num_ctx": 4096},
        "reasoning": {"model": "reason:14b", "tier": "quality", "vram_gb": 9.0, "num_ctx": 16384},
    },
    "routing": {"conversation": ["swift"]},
    "thinking": {"default": False, "by_task_type": {}},
}


async def _consume_stream(response) -> list[dict]:
    events = []
    async for line in response.body_iterator:
        text = line if isinstance(line, str) else line.decode("utf-8")
        for part in text.strip().split("\n"):
            if part.strip():
                events.append(json.loads(part))
    return events


@pytest.fixture
def patched_registry(monkeypatch):
    router = ModelRouter(_ROUTER_CONFIG)
    agent = _FakeAgent(router)
    import backend.core.agent_registry as agent_registry_module

    monkeypatch.setattr(
        agent_registry_module, "get_agent_registry", lambda: _FakeRegistry(agent),
    )
    return router


class TestStreamRoutePayload:
    @pytest.mark.asyncio
    async def test_role_in_payload_reaches_the_forced_decision(self, patched_registry):
        from backend.conversation import routes as conv_routes

        mgr = conv_routes._get_manager()  # noqa: SLF001
        session = mgr.create_session()

        response = await conv_routes.stream_message({
            "session_id": session.session_id, "message": "bonjour", "role": "reasoning",
        })
        assert response.headers["X-Hermes-Model"] == "reason:14b"
        events = await _consume_stream(response)
        assert any(e["kind"] == "content" and e["text"] == "réponse" for e in events)

    @pytest.mark.asyncio
    async def test_context_usage_is_reported_in_the_done_event(self, patched_registry):
        from backend.conversation import routes as conv_routes

        mgr = conv_routes._get_manager()  # noqa: SLF001
        session = mgr.create_session()

        response = await conv_routes.stream_message({
            "session_id": session.session_id, "message": "bonjour",
        })
        events = await _consume_stream(response)
        done = next(e for e in events if e["kind"] == "done")

        assert done["context"]["window"] == 4096  # swift's real configured num_ctx
        assert done["context"]["used_tokens_estimate"] > 0

    @pytest.mark.asyncio
    async def test_unknown_role_reports_a_real_error_not_a_silent_fallback(self, patched_registry):
        from backend.conversation import routes as conv_routes

        mgr = conv_routes._get_manager()  # noqa: SLF001
        session = mgr.create_session()

        response = await conv_routes.stream_message({
            "session_id": session.session_id, "message": "bonjour", "role": "not-a-role",
        })
        events = await _consume_stream(response)
        assert events[0]["kind"] == "error"
        assert "not-a-role" in events[0]["error"]
