"""Thin async wrapper around the local Ollama REST API.

Kept deliberately small and dependency-light so it can be swapped for a
fake/mock implementation in tests (see backend/tests/conftest.py) without
touching any of the callers. Nothing here hardcodes a model name.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx


class OllamaClientProtocol(Protocol):
    """Interface every Ollama client (real or fake) must satisfy."""

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
    ) -> None:
        """`always_loaded_models` holds the Ollama tags that should never be
        evicted for idleness — config/models.yaml's `always_loaded: true`
        roles (swift, embedding). They get keep_alive: -1 instead of the
        global expiry, so the routing/classification pre-pass doesn't pay a
        cold load on every request after an idle gap (§22)."""
        self._base_url = base_url.rstrip("/")
        self._keep_alive = keep_alive
        self._always_loaded = always_loaded_models or set()
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    def _keep_alive_for(self, model: str) -> Any:
        """-1 means "hold in VRAM indefinitely" in Ollama's API; anything
        else is passed through as the configured duration string."""
        return -1 if model in self._always_loaded else self._keep_alive

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        think: bool | None = None,
    ) -> AsyncIterator[str]:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if num_ctx is not None:
            options["num_ctx"] = num_ctx

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

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("done"):
                    break
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

    async def list_running_models(self) -> list[dict[str, Any]]:
        response = await self._client.get("/api/ps")
        response.raise_for_status()
        return response.json().get("models", [])

    async def list_local_models(self) -> list[dict[str, Any]]:
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        return response.json().get("models", [])

    async def aclose(self) -> None:
        await self._client.aclose()
