"""Voice package for Hermes OS (HOS-064) - Voice Ready Architecture.

Provides interfaces for Speech-to-Text and Text-to-Speech providers
without requiring implementation. Ready for Whisper, Piper, or cloud providers.
"""

from .speech_to_text import SpeechToTextProvider
from .text_to_speech import TextToSpeechProvider

__all__ = [
    "SpeechToTextProvider",
    "TextToSpeechProvider",
]
