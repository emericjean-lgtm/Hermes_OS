"""Text-to-Speech Provider Interface for Hermes OS (HOS-064).

Abstract interface for TTS providers. Supports Piper (local),
cloud providers, and custom implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


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
