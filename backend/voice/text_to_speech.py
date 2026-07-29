"""Text-to-Speech Provider Interface for Hermes OS (HOS-064).

Abstract interface for TTS providers. Supports Piper (local),
cloud providers, and custom implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TextToSpeechProvider(ABC):
    """Abstract interface for text-to-speech conversion."""

    @abstractmethod
    def synthesize(self, text: str, voice: str = "default",
                   language: str = "fr") -> bytes:
        """Synthesize text to speech audio bytes."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this TTS provider is available."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return provider name."""
        ...

    def get_voices(self) -> list[str]:
        return ["default", "female", "male"]


class PiperProvider(TextToSpeechProvider):
    """Local Piper TTS provider (interface only)."""

    def __init__(self, model_path: str = ""):
        self._model_path = model_path

    def synthesize(self, text: str, voice: str = "default",
                   language: str = "fr") -> bytes:
        raise NotImplementedError(
            "Piper provider requires: pip install piper-tts"
        )

    def is_available(self) -> bool:
        try:
            import piper  # type: ignore
            return True
        except ImportError:
            return False

    def get_name(self) -> str:
        return "piper"

    def get_voices(self) -> list[str]:
        return ["default"]


class CloudTTSProvider(TextToSpeechProvider):
    """Cloud-based TTS provider (interface only)."""

    def __init__(self, api_key: str = "", provider: str = "google"):
        self._api_key = api_key
        self._provider = provider

    def synthesize(self, text: str, voice: str = "default",
                   language: str = "fr") -> bytes:
        raise NotImplementedError(
            f"Cloud TTS ({self._provider}) requires API key configuration"
        )

    def is_available(self) -> bool:
        return bool(self._api_key)

    def get_name(self) -> str:
        return f"cloud_{self._provider}"
