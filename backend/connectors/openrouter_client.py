"""Thin async wrapper around OpenRouter's OpenAI-compatible REST API.

Scope is deliberately narrow: this project only ever talks to OpenRouter's
free (":free", zero-priced) model pool, as a rare escalation when no local
Ollama model is viable — see ``AdaptiveRouter``'s cloud gate
(backend/model_intelligence/adaptive_router.py) and
``CloudModelCatalog`` (backend/model_intelligence/cloud_catalog.py), which is
the only thing that discovers *which* models are free and feeds them into the
same ``ModelProfiler`` the local roles use.

All endpoint shapes here (``/chat/completions``, ``/models``, ``/key``,
pricing fields, the 429 error body, SSE ``finish_reason: "error"`` on a
mid-stream provider failure) were confirmed against OpenRouter's live API and
docs, not assumed — see CHANGELOG for the HOS-066C entry.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.connectors.ollama_client import StreamChunk
from backend.ral.capabilities import ChatResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# Same reasoning as ollama_client.py's _CONNECTION_ERRORS: retry a dropped
# connection, never retry a definitive rejection (4xx) — a 429 or 400 will
# return exactly the same answer on a second attempt.
_CONNECTION_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                      httpx.RemoteProtocolError, httpx.PoolTimeout)

DEFAULT_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 0.5


def _backoff_delay(attempt: int) -> float:
    return min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), 4.0)


class OpenRouterUnavailableError(RuntimeError):
    """OpenRouter could not serve the request.

    Named distinctly from Ollama's own error so callers (RealTaskExecutor)
    can tell "the cloud escalation failed" from "the local runtime failed" —
    the former has a real fallback (local), the latter does not.
    """


class OpenRouterQuotaExhaustedError(OpenRouterUnavailableError):
    """The shared daily/per-minute free-tier quota is exhausted (HTTP 429).

    OpenRouter's free-tier limit (20 req/min always; 50 or 1000 req/day with
    >=$10 lifetime credit) is one pool shared across every ``:free`` model
    under the API key — this is *not* raised per-model, so rotating to a
    different free model cannot work around it. A named subclass rather than
    a bare OpenRouterUnavailableError so a caller that cares can distinguish
    "no budget left" from "this model/request failed for another reason",
    though both trigger the same automatic local fallback in practice.
    """


class OpenRouterClient:
    """Real implementation, talking to OpenRouter's hosted API over HTTPS."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        app_title: str = "Hermes OS",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """``transport`` is a test seam (``httpx.MockTransport``) — never set
        in production, where the real network transport applies."""
        if not api_key:
            raise ValueError(
                "OpenRouterClient requires a non-empty api_key — set "
                "OPENROUTER_API_KEY in .env to enable cloud escalation, or "
                "leave it unset to stay local-only."
            )
        self._base_url = base_url.rstrip("/")
        self._max_attempts = max(1, max_attempts)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if app_title:
            # Purely informational (shows up in OpenRouter's own dashboard for
            # this key) — not required for the API to function.
            headers["X-Title"] = app_title
        self._client = httpx.AsyncClient(
            base_url=self._base_url, timeout=timeout, headers=headers,
            transport=transport,
        )

    @classmethod
    def from_settings(cls) -> "OpenRouterClient | None":
        """None when OPENROUTER_API_KEY isn't configured — the one, shared
        way every consumer (agents, mission planner, task executor) checks
        whether cloud escalation is available at all, so "is it configured"
        is answered identically everywhere rather than three slightly
        different guards drifting apart."""
        from backend.core.config import get_settings

        settings = get_settings()
        if not settings.openrouter_api_key:
            return None
        return cls(settings.openrouter_api_key)

    # ── chat ─────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        num_ctx: int | None = None,
    ) -> ChatResponse:
        """Non-streaming completion, capturing OpenRouter's own reported
        ``usage`` counters (real prompt/completion token counts — not the
        character-count estimate RealTaskExecutor falls back to when a
        runtime doesn't report them)."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        data = await self._post_with_retry("/chat/completions", payload)
        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterUnavailableError(
                f"OpenRouter returned no choices for model {model!r}: {data!r}"
            )
        message = choices[0].get("message") or {}
        content = str(message.get("content") or "")
        usage = data.get("usage") or {}
        metadata: dict[str, Any] = {
            "model": str(data.get("model") or model),
            "provider": "openrouter",
        }
        # HOS-242 : OpenRouter n'execute rien lui-meme — il route vers un
        # fournisseur amont (Together, DeepInfra, Fireworks…) et le nomme
        # dans un champ de premier niveau de la reponse. Confondre les deux
        # revenait a dire « openrouter » la ou trois hebergeurs differents
        # peuvent avoir servi trois reponses, avec trois latences et trois
        # comportements.
        #
        # Lu au champ structure, jamais devine : absent, il reste absent.
        # Aucune cle n'etant configuree sur cette installation, ce champ
        # n'a **pas** ete observe sur une reponse reelle ; la lecture est
        # donc defensive et son absence n'invente rien.
        amont = str(data.get("provider") or "").strip()
        if amont:
            metadata["fournisseur"] = amont
        if usage.get("prompt_tokens") is not None:
            metadata["prompt_tokens"] = int(usage["prompt_tokens"])
        if usage.get("completion_tokens") is not None:
            metadata["completion_tokens"] = int(usage["completion_tokens"])
        return ChatResponse(content=content, metadata=metadata)

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Content tokens only — mirrors OllamaClient.chat_stream's contract."""
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
        """Streams via Server-Sent Events (``data: {...}`` lines, terminated
        by ``data: [DONE]``). ``num_ctx``/``think`` are accepted for
        signature parity with OllamaClientProtocol but have no OpenRouter
        equivalent (context length is fixed per model, not requestable;
        reasoning-token streaming is a per-model OpenRouter feature this
        client does not opt into, since its shape hasn't been verified) —
        both are silently ignored rather than guessed at.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p

        started = False
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client.stream(
                    "POST", "/chat/completions", json=payload
                ) as response:
                    if response.status_code != 200:
                        raw = await response.aread()
                        self._raise_for_status(response.status_code, raw)
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        # A mid-stream provider failure arrives as a normal
                        # SSE event with finish_reason "error", not a clean
                        # HTTP error — confirmed against OpenRouter's docs.
                        if choice.get("finish_reason") == "error":
                            raise OpenRouterUnavailableError(
                                "OpenRouter reported a mid-stream provider "
                                f"error for model {model!r}: {choice!r}"
                            )
                        content = (choice.get("delta") or {}).get("content") or ""
                        if content:
                            started = True
                            yield StreamChunk("content", content)
                return
            except _CONNECTION_ERRORS as exc:
                if started or attempt >= self._max_attempts:
                    raise OpenRouterUnavailableError(
                        f"OpenRouter unreachable after {attempt} attempt(s): "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                await self._sleep(_backoff_delay(attempt))

    @staticmethod
    async def _sleep(seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)

    def _raise_for_status(self, status_code: int, raw: bytes) -> None:
        try:
            body = json.loads(raw.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        message = ((body.get("error") or {}).get("message")
                   or raw.decode("utf-8", errors="replace")[:300])
        if status_code == 429:
            raise OpenRouterQuotaExhaustedError(
                f"OpenRouter rate limit exceeded (HTTP 429): {message}"
            )
        raise OpenRouterUnavailableError(
            f"OpenRouter returned HTTP {status_code}: {message}"
        )

    async def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._client.post(path, json=payload)
                if response.status_code != 200:
                    self._raise_for_status(response.status_code, response.content)
                return response.json()
            except _CONNECTION_ERRORS as exc:
                if attempt >= self._max_attempts:
                    raise OpenRouterUnavailableError(
                        f"OpenRouter unreachable after {attempt} attempt(s): "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                await self._sleep(_backoff_delay(attempt))

    # Catalogue discovery (GET /models) and quota checks (GET /key) are
    # deliberately not duplicated here — CloudModelCatalog
    # (backend/model_intelligence/cloud_catalog.py) makes those two calls
    # itself, synchronously, since AdaptiveRouter.recommend() (its only
    # caller) is sync. This client stays focused on the one thing that
    # actually needs async: chat completions.

    async def aclose(self) -> None:
        await self._client.aclose()
