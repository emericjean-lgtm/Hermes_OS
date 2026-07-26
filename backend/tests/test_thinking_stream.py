"""§22.1 — surfacing the reasoning phase instead of leaving a silent wait.

Measured: a code_analysis task spent 42 s reasoning before its first
visible word. The reasoning was always there, in `message.thinking`;
`chat_stream` simply dropped it.

The bulk of these tests pin what must NOT change. Ten agents parse the
answer as JSON, and letting reasoning text into that stream would corrupt
every one of them — silently, since it would still look like output.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.connectors.ollama_client import OllamaClient, StreamChunk

pytestmark = pytest.mark.asyncio


def _body(*pairs):
    lines = [json.dumps({"message": {kind: text}}) for kind, text in pairs]
    lines.append(json.dumps({"done": True}))
    return "\n".join(lines) + "\n"


def _client(body: str):
    client = OllamaClient("http://127.0.0.1:11434")
    client._client = httpx.AsyncClient(
        base_url="http://127.0.0.1:11434",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)),
    )
    return client


MIXED = _body(("thinking", "je réfléchis"), ("thinking", " encore"), ("content", "Paris"))


# ── what must not change ─────────────────────────────────────────────
async def test_chat_stream_still_yields_content_only():
    """The contract every agent depends on. If reasoning leaked in here,
    classify/verify/extract would parse it as part of the answer."""
    tokens = [t async for t in _client(MIXED).chat_stream("m", [])]

    assert tokens == ["Paris"]


async def test_chat_stream_is_unchanged_when_there_is_no_reasoning():
    tokens = [t async for t in _client(_body(("content", "a"), ("content", "b"))).chat_stream("m", [])]

    assert tokens == ["a", "b"]


# ── the new channel ──────────────────────────────────────────────────
async def test_chat_events_yields_both_kinds_in_order():
    chunks = [c async for c in _client(MIXED).chat_events("m", [])]

    assert chunks == [
        StreamChunk("thinking", "je réfléchis"),
        StreamChunk("thinking", " encore"),
        StreamChunk("content", "Paris"),
    ]


async def test_reasoning_arrives_before_the_answer():
    """The whole point: something to show while the model thinks."""
    chunks = [c async for c in _client(MIXED).chat_events("m", [])]

    assert chunks[0].kind == "thinking"
    assert chunks[-1].kind == "content"


# ── the retry guarantee still holds ──────────────────────────────────
class _DropsAfterThinking(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"message":{"thinking":"je r\u00e9fl\u00e9chis"}}\n'
        raise httpx.RemoteProtocolError("peer closed connection")


async def test_a_drop_after_reasoning_is_not_retried(monkeypatch):
    """`started` must trip on reasoning too. Tracking only content would
    let a reconnect replay the reasoning the caller already received."""
    import asyncio

    monkeypatch.setattr(asyncio, "sleep", lambda *_: asyncio.sleep(0))
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(200, stream=_DropsAfterThinking())
        return httpx.Response(200, text=MIXED)

    client = OllamaClient("http://127.0.0.1:11434")
    client._client = httpx.AsyncClient(
        base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(handler)
    )

    from backend.connectors.ollama_client import OllamaUnavailableError

    collected = []
    with pytest.raises(OllamaUnavailableError, match="duplicate"):
        async for chunk in client.chat_events("m", []):
            collected.append(chunk)

    assert collected == [StreamChunk("thinking", "je réfléchis")]
    assert attempts["n"] == 1


# ── the metrics must not silently change meaning ─────────────────────
async def test_reasoning_chunks_do_not_inflate_the_token_count():
    """tokens_used and tokens_per_second stay content-only. Counting
    reasoning would leave both fields named the same, typed the same, and
    measuring something else — throughput would look *best* on exactly
    the requests that made the user wait longest."""
    from backend.core.audit_log import Timer

    timer = Timer()
    _ = [c async for c in timer.measure_events(_client(MIXED).chat_events("m", []))]

    assert timer.tokens == 1
    assert timer.first_token_ms is not None      # first content
    assert timer.first_thinking_ms is not None   # first reasoning
    assert timer.first_thinking_ms <= timer.first_token_ms
