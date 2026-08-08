"""Tests for HOS-072 — OllamaClient.unload_model().

Real signal to unload a model immediately (keep_alive: 0 with no prompt),
instead of Hermes only ever waiting for Ollama's own idle timer. Fully
hermetic: a mock httpx transport swapped into the client's internal
AsyncClient, no real Ollama needed.
"""
from __future__ import annotations

import httpx
import pytest

from backend.connectors.ollama_client import OllamaClient, OllamaUnavailableError


def _swap_transport(client: OllamaClient, handler) -> None:
    """OllamaClient builds its own httpx.AsyncClient internally with no
    transport injection point — swap the private attribute after
    construction, the same technique used elsewhere in this codebase for
    testing thin real-HTTP wrappers without a live server."""
    client._client = httpx.AsyncClient(  # noqa: SLF001
        base_url=client._base_url, transport=httpx.MockTransport(handler),  # noqa: SLF001
    )


class TestUnloadModel:
    @pytest.mark.asyncio
    async def test_sends_keep_alive_zero_with_no_prompt(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["json"] = httpx.Request.read(request) and request.content
            return httpx.Response(200, json={"done": True})

        client = OllamaClient("http://fake-ollama")
        _swap_transport(client, handler)
        await client.unload_model("qwen3.5:9b")

        assert captured["url"].endswith("/api/generate")
        import json as _json
        body = _json.loads(captured["json"])
        assert body == {"model": "qwen3.5:9b", "keep_alive": 0}
        assert "prompt" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_connection_failure_raises_ollama_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = OllamaClient("http://fake-ollama", max_attempts=1)
        _swap_transport(client, handler)
        with pytest.raises(OllamaUnavailableError):
            await client.unload_model("qwen3.5:9b")
        await client.aclose()
