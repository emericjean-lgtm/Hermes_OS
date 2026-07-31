"""Speech-to-Text Provider Interface for Hermes OS (HOS-064).

Abstract interface for STT providers. Supports Whisper (local),
cloud providers, and custom implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SpeechToTextProvider(ABC):
    """Abstract interface for speech-to-text conversion."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "fr") -> str:
        """Transcribe audio file to text."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this STT provider is available."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return provider name."""
        ...

    def get_languages(self) -> list[str]:
        return ["fr", "en", "de", "es", "it"]


class WhisperProvider(SpeechToTextProvider):
    """Local Whisper STT provider (interface only)."""

    def transcribe(self, audio_path: str, language: str = "fr") -> str:
        raise NotImplementedError(
            "Whisper provider requires: pip install openai-whisper"
        )

    def is_available(self) -> bool:
        try:
            import whisper  # type: ignore
            return True
        except ImportError:
            return False

    def get_name(self) -> str:
        return "whisper"


class CloudSTTProvider(SpeechToTextProvider):
    """Cloud-based STT provider (interface only)."""

    def __init__(self, api_key: str = "", provider: str = "google"):
        self._api_key = api_key
        self._provider = provider

    def transcribe(self, audio_path: str, language: str = "fr") -> str:
        raise NotImplementedError(
            f"Cloud STT ({self._provider}) requires API key configuration"
        )

    def is_available(self) -> bool:
        return bool(self._api_key)

    def get_name(self) -> str:
        return f"cloud_{self._provider}"
