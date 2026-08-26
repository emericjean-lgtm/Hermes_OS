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


# HOS-175 : `WhisperProvider`, `PiperProvider` et leurs pendants cloud
# vivaient ici depuis HOS-064. Chacun levait `NotImplementedError` et
# annoncait sa disponibilite sur un simple `import`.
#
# Le defaut est reste latent trois jours : tant que la dependance manquait,
# `is_available()` rendait False et personne ne s'en apercevait. Installer
# `piper-tts` l'a revele d'un coup — la classe se declarait disponible et
# aurait leve au premier appel.
#
# Les implementations reelles vivent dans `backend/voice/locale.py`, avec
# leurs modeles mesures. Garder ces souches a cote aurait laisse deux
# reponses a une meme question, dont une fausse.
