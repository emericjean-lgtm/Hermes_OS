"""Thin async wrapper around the local Ollama REST API.

Kept deliberately small and dependency-light so it can be swapped for a
fake/mock implementation in tests (see backend/tests/conftest.py) without
touching any of the callers. Nothing here hardcodes a model name.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

import httpx

from backend.ral.capabilities import ChatResponse


@dataclass(frozen=True)
class StreamChunk:
    """One piece of a response, with what kind of piece it is.

    A reasoning model emits its chain-of-thought in `message.thinking`,
    separate from `message.content`. `chat_stream` yields content only —
    which is right for the agents that parse the answer as JSON, and
    wrong for a human, who then stares at nothing for the whole reasoning
    phase (measured: 42 s on a code_analysis task).

    So the two live at different levels: `chat_events` yields everything,
    tagged; `chat_stream` filters it down to content and keeps its old
    contract byte for byte.
    """

    kind: Literal["thinking", "content"]
    text: str

# Retried on: Ollama not listening, dropped connection, timeout (§19.1,
# acceptance criterion T11). Deliberately NOT retried: httpx.HTTPStatusError.
# A 404 for a missing model or a 400 for a malformed request will return
# exactly the same answer three times — retrying only delays a clear
# error and hides its cause behind "3 attempts failed".
_CONNECTION_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                      httpx.RemoteProtocolError, httpx.PoolTimeout)

DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5

# Ollama's own default is 4096 (some Modelfiles ship 2048), and a prompt
# longer than the active window is silently truncated from the *front* —
# no error, no warning, just the earliest context gone. bench_context.py's
# needle-in-a-haystack probe confirmed this concretely: a fact placed near
# the top of a ~6k-word document was unretrievable at num_ctx=4096 purely
# from truncation, not model capability (prompt_eval_count stopped growing
# at ~2050 tokens, well short of the actual prompt). None of this codebase's
# 20+ chat_events()/chat_stream() call sites ever passed num_ctx, so every
# one of them was silently getting Ollama's low default. 8192 is the
# empirically-confirmed floor at which realistic conversation/task prompts
# stop truncating; callers with a specific, larger need can still override
# by passing num_ctx explicitly.
DEFAULT_NUM_CTX = 8192


def _backoff_delay(attempt: int) -> float:
    """0.5s, then 1s — exponential, capped. Ollama loading a model is the
    common cause of an early refusal, and that resolves in seconds; a
    longer wait would just stall a user who would rather see the error."""
    return min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), 4.0)


def _unavailable_message(base_url: str, attempts: int, exc: Exception, *,
                         mid_stream: bool = False) -> str:
    """§19.1 asks for a clear notification, not a bare traceback."""
    if mid_stream:
        return (
            f"Ollama connection lost mid-response ({type(exc).__name__}: {exc}). "
            "Not retried on purpose: part of the answer was already delivered, "
            "and repeating the request would duplicate it. Re-ask to get a "
            "complete answer."
        )
    return (
        f"Ollama unreachable at {base_url} after {attempts} attempt(s) "
        f"({type(exc).__name__}: {exc}). Check that it is running — "
        "`ollama ps` should answer, and the service listens on port 11434."
    )


class OllamaUnavailableError(RuntimeError):
    """Ollama could not be reached, after the configured retries.

    A named type rather than a bare httpx error so callers can tell "the
    inference server is down" from "the model refused the request" — the
    two need different reactions, and only the first is worth retrying.
    """


@runtime_checkable
class OllamaClientProtocol(Protocol):
    """Interface every Ollama client (real or fake) must satisfy."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> ChatResponse: ...

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[str]: ...

    def chat_events(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def list_running_models(self) -> list[dict[str, Any]]: ...

    async def list_local_models(self) -> list[dict[str, Any]]: ...


class OllamaClient:
    """Real implementation, talking to a live Ollama server over HTTP."""

    def __init__(
        self,
        base_url: str,
        *,
        keep_alive: str = "10m",
        timeout: float = 120.0,
        always_loaded_models: set[str] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        default_num_ctx: int = DEFAULT_NUM_CTX,
    ) -> None:
        """`always_loaded_models` holds the Ollama tags that should never be
        evicted for idleness — config/models.yaml's `always_loaded: true`
        roles (swift, embedding). They get keep_alive: -1 instead of the
        global expiry, so the routing/classification pre-pass doesn't pay a
        cold load on every request after an idle gap (§22).

        `default_num_ctx` is applied in chat_events() whenever a caller
        does not pass num_ctx explicitly — see DEFAULT_NUM_CTX for why that
        matters."""
        self._base_url = base_url.rstrip("/")
        self._keep_alive = keep_alive
        self._always_loaded = always_loaded_models or set()
        self._max_attempts = max(1, max_attempts)
        self._default_num_ctx = default_num_ctx
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    def _keep_alive_for(self, model: str) -> Any:
        """-1 means "hold in VRAM indefinitely" in Ollama's API; anything
        else is passed through as the configured duration string."""
        return -1 if model in self._always_loaded else self._keep_alive

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> ChatResponse:
        """Non-streaming chat that collects all tokens and returns a
        :class:`ChatResponse`.

        If ``model`` is ``None`` the client's endpoint is expected to
        provide a default — callers that want a specific model should
        always pass it explicitly.
        """
        used_model = model or "default"
        tokens: list[str] = []
        async for token in self.chat_stream(used_model, messages):
            tokens.append(token)
        content = "".join(tokens)
        return ChatResponse(
            content=content,
            metadata={"model": used_model, "provider": "ollama"},
        )

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Content tokens only — the long-standing contract.

        Every agent that parses the answer (classification, verification,
        extraction) depends on nothing but content arriving here, so this
        stays a strict filter over `chat_events` rather than gaining a
        mode of its own.
        """
        async for chunk in self.chat_events(model, messages, **kwargs):
            if chunk.kind == "content":
                yield chunk.text

    async def chat_events(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[StreamChunk]:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        # Always set, never omitted: an omitted num_ctx falls back to
        # Ollama's own default (4096, sometimes 2048 per-Modelfile), which
        # silently truncates long prompts from the front — see
        # DEFAULT_NUM_CTX. num_ctx=None here means "use this client's
        # configured default", not "let Ollama decide".
        options["num_ctx"] = num_ctx if num_ctx is not None else self._default_num_ctx

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self._keep_alive_for(model),
            "options": options,
        }
        # think=True asks Ollama to return a reasoning-capable model's
        # chain-of-thought in message.thinking, separate from
        # message.content — without it, some reasoning models (confirmed
        # on real hardware with phi4-reasoning:14b-q4_K_M, Aegis's
        # security-role model) inline the whole reasoning trace into
        # content instead, which is what chat_stream yields below. Only
        # sent when explicitly requested (None omits the field
        # entirely) — not every model supports it, and callers that
        # don't need the distinction shouldn't pay for asking.
        if think is not None:
            payload["think"] = think

        # The retry wraps only the *connection*, never the stream. Once a
        # token has been yielded the caller has it, and re-running the
        # request would emit those tokens a second time — a duplicated
        # answer is worse than a clean failure. `started` is the latch
        # that makes that guarantee explicit rather than incidental.
        started = False
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client.stream("POST", "/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if chunk.get("done"):
                            return
                        message = chunk.get("message", {})
                        # `started` trips on *any* emitted chunk, reasoning
                        # included: once the caller has received something,
                        # a retry would repeat it. Tracking only content
                        # here would let a reconnect replay the reasoning.
                        thinking = message.get("thinking", "")
                        if thinking:
                            started = True
                            yield StreamChunk("thinking", thinking)
                        content = message.get("content", "")
                        if content:
                            started = True
                            yield StreamChunk("content", content)
                return
            except _CONNECTION_ERRORS as exc:
                if started or attempt >= self._max_attempts:
                    raise OllamaUnavailableError(_unavailable_message(
                        self._base_url, attempt, exc, mid_stream=started
                    )) from exc
                await asyncio.sleep(_backoff_delay(attempt))

    async def _get_json_with_retry(self, path: str) -> dict[str, Any]:
        """GET a small JSON endpoint, retrying connection failures.

        Safe to retry wholesale, unlike chat_stream: these return one
        response with no partial output a caller could already have acted
        on.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.get(path)
                response.raise_for_status()
                return response.json()
            except _CONNECTION_ERRORS as exc:
                if attempt >= self._max_attempts:
                    raise OllamaUnavailableError(
                        _unavailable_message(self._base_url, attempt, exc)
                    ) from exc
                await asyncio.sleep(_backoff_delay(attempt))

    async def list_running_models(self) -> list[dict[str, Any]]:
        return (await self._get_json_with_retry("/api/ps")).get("models", [])

    async def list_local_models(self) -> list[dict[str, Any]]:
        return (await self._get_json_with_retry("/api/tags")).get("models", [])

    async def aclose(self) -> None:
        await self._client.aclose()
