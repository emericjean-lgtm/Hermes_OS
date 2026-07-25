"""§19.1 / acceptance criterion T11 — retry Ollama with backoff.

The interesting half is what must *not* be retried. Re-running a request
that already streamed tokens would duplicate them, and re-running a 404
for a missing model just delays a clear error behind "3 attempts failed".
Both are pinned below.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.connectors.ollama_client import (
    DEFAULT_MAX_ATTEMPTS,
    OllamaClient,
    OllamaUnavailableError,
    _backoff_delay,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """Backoff is real in production and instant here — otherwise these
    tests would spend their time asleep and stop being run."""
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


def _client(handler, **kwargs):
    client = OllamaClient("http://127.0.0.1:11434", **kwargs)
    client._client = httpx.AsyncClient(
        base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(handler)
    )
    return client


def _stream_body(*chunks):
    import json

    lines = [json.dumps({"message": {"content": c}}) for c in chunks]
    lines.append(json.dumps({"done": True}))
    return "\n".join(lines) + "\n"


async def _drain(client, **kwargs):
    return [token async for token in client.chat_stream("m", [{"role": "user", "content": "x"}], **kwargs)]


# ── the retry itself ─────────────────────────────────────────────────
async def test_recovers_when_ollama_comes_back(no_real_sleeping):
    """The T11 scenario: the server is down, then answers."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, text=_stream_body("bonjour"))

    tokens = await _drain(_client(handler))

    assert tokens == ["bonjour"]
    assert attempts["n"] == 3


async def test_gives_up_after_three_attempts(no_real_sleeping):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        raise httpx.ConnectError("connection refused")

    with pytest.raises(OllamaUnavailableError):
        await _drain(_client(handler))

    assert attempts["n"] == DEFAULT_MAX_ATTEMPTS == 3


async def test_backoff_grows_between_attempts(no_real_sleeping):
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError):
        await _drain(_client(handler))

    # Two waits for three attempts, and the second is longer.
    assert len(no_real_sleeping) == 2
    assert no_real_sleeping[1] > no_real_sleeping[0]


async def test_backoff_is_capped():
    """Unbounded exponential backoff would strand a user for minutes.
    (async only to satisfy the module-level asyncio mark; the function
    under test is synchronous.)"""
    assert _backoff_delay(1) == 0.5
    assert _backoff_delay(2) == 1.0
    assert _backoff_delay(20) <= 4.0


async def test_the_error_says_what_to_check(no_real_sleeping):
    """§19.1 asks for a clear notification, not a traceback."""
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError) as caught:
        await _drain(_client(handler))

    message = str(caught.value)
    assert "127.0.0.1:11434" in message
    assert "3 attempt" in message
    assert "ollama ps" in message


# ── what must NOT be retried ─────────────────────────────────────────
class _DropsMidStream(httpx.AsyncByteStream):
    """Yields one valid line, then drops the connection.

    A merely *truncated* body would not do: it ends cleanly and raises
    nothing, so it would test the wrong thing. This reproduces the real
    failure — the socket dying with tokens already delivered.
    """

    async def __aiter__(self):
        yield b'{"message":{"content":"d\\u00e9but"}}\n'
        raise httpx.RemoteProtocolError("peer closed connection")


async def test_tokens_already_delivered_are_never_duplicated(no_real_sleeping):
    """The load-bearing guarantee. A connection dropped mid-answer must
    fail cleanly rather than replay the tokens the caller already has."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(200, stream=_DropsMidStream())
        return httpx.Response(200, text=_stream_body("début", "suite"))

    client = _client(handler)
    collected = []
    with pytest.raises(OllamaUnavailableError, match="duplicate"):
        async for token in client.chat_stream("m", [{"role": "user", "content": "x"}]):
            collected.append(token)

    assert collected == ["début"]  # emitted once, never twice
    assert attempts["n"] == 1  # no second request at all
    assert no_real_sleeping == []  # and no backoff wait either


async def test_an_http_error_is_not_retried(no_real_sleeping):
    """A 404 for a missing model answers identically three times —
    retrying only hides the cause."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(404, text="model not found")

    with pytest.raises(httpx.HTTPStatusError):
        await _drain(_client(handler))

    assert attempts["n"] == 1
    assert no_real_sleeping == []


async def test_a_successful_call_never_sleeps(no_real_sleeping):
    def handler(request):
        return httpx.Response(200, text=_stream_body("ok"))

    assert await _drain(_client(handler)) == ["ok"]
    assert no_real_sleeping == []


# ── the small JSON endpoints ─────────────────────────────────────────
async def test_list_running_models_retries(no_real_sleeping):
    """Safe to retry wholesale: one response, no partial output."""
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"models": [{"name": "qwen3:1.7b"}]})

    models = await _client(handler).list_running_models()

    assert models == [{"name": "qwen3:1.7b"}]
    assert attempts["n"] == 2


async def test_list_local_models_reports_a_dead_server_clearly(no_real_sleeping):
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError, match="unreachable"):
        await _client(handler).list_local_models()


# ── configurability ──────────────────────────────────────────────────
async def test_attempts_are_configurable(no_real_sleeping):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError):
        await _drain(_client(handler, max_attempts=5))

    assert attempts["n"] == 5


async def test_a_single_attempt_disables_retrying(no_real_sleeping):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        raise httpx.ConnectError("refused")

    with pytest.raises(OllamaUnavailableError):
        await _drain(_client(handler, max_attempts=0))  # clamped to 1

    assert attempts["n"] == 1
    assert no_real_sleeping == []
