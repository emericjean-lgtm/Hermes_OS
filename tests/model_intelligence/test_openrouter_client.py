"""Tests for OpenRouterClient (HOS-066C).

No network I/O: every request goes through httpx.MockTransport, a real
httpx testing seam — this exercises the actual request-building, SSE
parsing, and error-mapping code, not a hand-rolled stand-in for it.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.connectors.openrouter_client import (
    OpenRouterClient,
    OpenRouterQuotaExhaustedError,
    OpenRouterUnavailableError,
)


def _client(handler, **kwargs) -> OpenRouterClient:
    return OpenRouterClient(
        "test-key", transport=httpx.MockTransport(handler), **kwargs,
    )


class TestConstruction:
    def test_rejects_empty_api_key(self):
        with pytest.raises(ValueError):
            OpenRouterClient("")


class TestChat:
    @pytest.mark.asyncio
    async def test_returns_content_and_real_usage_counts(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/v1/chat/completions"
            body = json.loads(request.content)
            assert body["model"] == "deepseek/deepseek-chat-v3.1:free"
            assert body["stream"] is False
            return httpx.Response(200, json={
                "model": "deepseek/deepseek-chat-v3.1:free",
                "choices": [{"message": {"content": "hello from the cloud"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            })

        client = _client(handler)
        response = await client.chat(
            [{"role": "user", "content": "hi"}],
            model="deepseek/deepseek-chat-v3.1:free",
        )
        assert response.content == "hello from the cloud"
        assert response.metadata["provider"] == "openrouter"
        assert response.metadata["prompt_tokens"] == 12
        assert response.metadata["completion_tokens"] == 4
        await client.aclose()

    @pytest.mark.asyncio
    async def test_no_choices_raises_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": []})

        client = _client(handler)
        with pytest.raises(OpenRouterUnavailableError):
            await client.chat([{"role": "user", "content": "hi"}], model="m")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_429_raises_quota_exhausted(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={
                "error": {"code": 429, "message": "Rate limit exceeded"},
            })

        client = _client(handler)
        with pytest.raises(OpenRouterQuotaExhaustedError):
            await client.chat([{"role": "user", "content": "hi"}], model="m")
        await client.aclose()

    @pytest.mark.asyncio
    async def test_other_http_error_raises_unavailable_not_quota(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "bad request"}})

        client = _client(handler)
        with pytest.raises(OpenRouterUnavailableError) as excinfo:
            await client.chat([{"role": "user", "content": "hi"}], model="m")
        assert not isinstance(excinfo.value, OpenRouterQuotaExhaustedError)
        await client.aclose()


class TestChatEvents:
    @pytest.mark.asyncio
    async def test_streams_content_chunks_from_sse(self):
        body = (
            b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
            b"data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body,
                                  headers={"content-type": "text/event-stream"})

        client = _client(handler)
        chunks = [c async for c in client.chat_events("m", [{"role": "user", "content": "hi"}])]
        assert [c.kind for c in chunks] == ["content", "content"]
        assert "".join(c.text for c in chunks) == "Hello"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_chat_stream_yields_text_only(self):
        body = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        client = _client(handler)
        tokens = [t async for t in client.chat_stream("m", [{"role": "user", "content": "hi"}])]
        assert tokens == ["hi"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_mid_stream_finish_reason_error_raises(self):
        body = (
            b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"error"}]}\n\n'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        client = _client(handler)
        with pytest.raises(OpenRouterUnavailableError):
            async for _ in client.chat_events("m", [{"role": "user", "content": "hi"}]):
                pass
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_200_before_streaming_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "slow down"}})

        client = _client(handler)
        with pytest.raises(OpenRouterQuotaExhaustedError):
            async for _ in client.chat_events("m", [{"role": "user", "content": "hi"}]):
                pass
        await client.aclose()
