from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml


class FakeOllamaClient:
    """Duck-types OllamaClientProtocol without any network I/O."""

    def __init__(
        self,
        running_models: list[str] | None = None,
        response_chunks: list[str] | None = None,
    ) -> None:
        self._running = running_models or []
        self._chunks = response_chunks or ["Hello", ", ", "world", "!"]
        self.last_chat_call: dict[str, Any] | None = None

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
    ) -> AsyncIterator[str]:
        self.last_chat_call = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        for chunk in self._chunks:
            yield chunk

    async def list_running_models(self) -> list[dict[str, Any]]:
        return [{"name": name} for name in self._running]

    async def list_local_models(self) -> list[dict[str, Any]]:
        return [{"name": name} for name in self._running]


@pytest.fixture
def fake_ollama_client() -> FakeOllamaClient:
    return FakeOllamaClient()


@pytest.fixture
def models_config() -> dict:
    repo_root = Path(__file__).resolve().parents[2]
    with (repo_root / "config" / "models.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)
