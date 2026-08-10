"""Tests for BaseAgent's real tool-calling loop (HOS-078 — Assistant web
search). Fully hermetic: a scripted fake Ollama client, no real inference,
no real network call — the real end-to-end behaviour (DuckDuckGo search,
gpt-oss:20b actually asking for and using it) was verified separately by
hand against live Ollama; this file locks in the round-trip mechanics.
"""
from __future__ import annotations

import pytest

from backend.agents.base_agent import BaseAgent, _MAX_TOOL_ROUNDS
from backend.connectors.ollama_client import StreamChunk
from backend.core.router import ModelRouter

CONFIG = {
    "roles": {"swift": {"model": "swift:1b", "tier": "turbo", "vram_gb": 1.0}},
    "routing": {"conversation": ["swift"]},
    "thinking": {"default": False, "by_task_type": {}},
}
_GEN_DEFAULTS = {"generation_defaults": {"standard": {"temperature": 0.6, "top_p": 0.95}}}

_TOOLS = [{"type": "function", "function": {"name": "web_search", "parameters": {}}}]


class _Agent(BaseAgent):
    name = "test-agent"

    @property
    def default_task_type(self):
        return "conversation"


class _ScriptedOllama:
    """Each call to chat_events() consumes the next scripted response in
    order — lets a test dictate exactly what the "model" does turn by
    turn (ask for a tool, then answer; or keep asking forever)."""

    def __init__(self, responses: list[list[StreamChunk]]) -> None:
        self._responses = list(responses)
        self.chat_calls: list[tuple] = []

    async def list_running_models(self):
        return []

    def chat_events(self, model, messages, **kwargs):
        self.chat_calls.append((model, [dict(m) for m in messages], kwargs))
        script = self._responses.pop(0) if self._responses else []

        async def gen():
            for chunk in script:
                yield chunk

        return gen()


def _tool_call_chunk(name: str = "web_search", arguments: dict | None = None) -> StreamChunk:
    return StreamChunk("tool_calls", "", tool_calls=[{
        "id": "call_1", "function": {"name": name, "arguments": arguments or {"query": "q"}},
    }])


@pytest.fixture
def router() -> ModelRouter:
    return ModelRouter(CONFIG)


class TestToolCallExecuted:
    @pytest.mark.asyncio
    async def test_tool_call_is_really_executed_and_result_fed_back(self, router):
        ollama = _ScriptedOllama(responses=[
            [_tool_call_chunk(arguments={"query": "Firestore rules"})],
            [StreamChunk("content", "Here is the answer.")],
        ])
        agent = _Agent(ollama, router, _GEN_DEFAULTS)
        executed: list[tuple[str, dict]] = []

        async def executor(name: str, arguments: dict) -> str:
            executed.append((name, arguments))
            return "real search result text"

        decision, events = await agent.respond_events(
            [{"role": "user", "content": "search something"}],
            task_type="conversation", tools=_TOOLS, tool_executor=executor,
        )
        chunks = [c async for c in events]

        assert executed == [("web_search", {"query": "Firestore rules"})]
        kinds = [c.kind for c in chunks]
        assert kinds == ["tool_calls", "tool_result", "content"]
        assert chunks[-1].text == "Here is the answer."

        # Second chat_events() call must have seen the real tool result,
        # not a placeholder — this is the actual round trip, not a stub.
        assert len(ollama.chat_calls) == 2
        second_call_messages = ollama.chat_calls[1][1]
        assert second_call_messages[-1] == {
            "role": "tool", "content": "real search result text", "tool_name": "web_search",
        }
        assert second_call_messages[-2]["tool_calls"][0]["function"]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_second_call_still_offers_tools(self, router):
        """A model that answers without a tool call in round 1 must still
        be offered tools in the very same round — this test's real
        assertion is on round 1, not a second round."""
        ollama = _ScriptedOllama(responses=[[StreamChunk("content", "no search needed")]])
        agent = _Agent(ollama, router, _GEN_DEFAULTS)

        async def executor(name, arguments):
            raise AssertionError("must not be called")

        decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}],
            task_type="conversation", tools=_TOOLS, tool_executor=executor,
        )
        chunks = [c async for c in events]
        assert [c.kind for c in chunks] == ["content"]
        assert ollama.chat_calls[0][2]["tools"] == _TOOLS
        assert len(ollama.chat_calls) == 1


class TestNoToolsRequested:
    @pytest.mark.asyncio
    async def test_content_only_response_ends_after_one_call(self, router):
        ollama = _ScriptedOllama(responses=[[StreamChunk("content", "plain answer")]])
        agent = _Agent(ollama, router, _GEN_DEFAULTS)

        async def executor(name, arguments):
            raise AssertionError("must not be called")

        _decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}],
            task_type="conversation", tools=_TOOLS, tool_executor=executor,
        )
        chunks = [c async for c in events]
        assert len(chunks) == 1
        assert len(ollama.chat_calls) == 1


class TestBoundedRounds:
    @pytest.mark.asyncio
    async def test_exhausting_rounds_forces_a_final_answer_without_tools(self, router):
        """A model that keeps asking for tools without ever answering
        (observed in practice) must not hang the response forever — after
        _MAX_TOOL_ROUNDS, one last call runs with no `tools` offered, so
        the model physically cannot ask again and must synthesize."""
        responses = [[_tool_call_chunk()] for _ in range(_MAX_TOOL_ROUNDS)]
        responses.append([StreamChunk("content", "forced final answer")])
        ollama = _ScriptedOllama(responses=responses)
        agent = _Agent(ollama, router, _GEN_DEFAULTS)

        async def executor(name, arguments):
            return "result"

        _decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}],
            task_type="conversation", tools=_TOOLS, tool_executor=executor,
        )
        chunks = [c async for c in events]

        assert chunks[-1].kind == "content"
        assert chunks[-1].text == "forced final answer"
        # _MAX_TOOL_ROUNDS scripted calls + 1 final call with no tools.
        assert len(ollama.chat_calls) == _MAX_TOOL_ROUNDS + 1
        assert "tools" not in ollama.chat_calls[-1][2]


class TestToolExecutorFailure:
    @pytest.mark.asyncio
    async def test_a_raising_tool_executor_is_reported_not_raised(self, router):
        ollama = _ScriptedOllama(responses=[
            [_tool_call_chunk()],
            [StreamChunk("content", "answered anyway")],
        ])
        agent = _Agent(ollama, router, _GEN_DEFAULTS)

        async def executor(name, arguments):
            raise RuntimeError("search backend is down")

        _decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}],
            task_type="conversation", tools=_TOOLS, tool_executor=executor,
        )
        chunks = [c async for c in events]
        tool_result = next(c for c in chunks if c.kind == "tool_result")
        assert "search backend is down" in tool_result.tool_calls[0]["result"]
        # The loop continued to a real second call rather than crashing.
        assert chunks[-1].text == "answered anyway"


class TestNoToolsOffered:
    @pytest.mark.asyncio
    async def test_omitting_tools_keeps_the_original_single_call_path(self, router):
        """tools=None (every pre-existing caller) must take the exact old
        path — no tool-calling machinery involved at all."""
        ollama = _ScriptedOllama(responses=[[StreamChunk("content", "answer")]])
        agent = _Agent(ollama, router, _GEN_DEFAULTS)

        _decision, events = await agent.respond_events(
            [{"role": "user", "content": "hi"}], task_type="conversation",
        )
        chunks = [c async for c in events]
        assert chunks[0].text == "answer"
        assert "tools" not in ollama.chat_calls[0][2] or ollama.chat_calls[0][2]["tools"] is None
