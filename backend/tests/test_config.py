from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.config import Settings


def test_rejects_empty_ollama_host():
    with pytest.raises(ValidationError, match="OLLAMA_HOST is empty"):
        Settings(ollama_host="")


def test_rejects_ollama_host_without_scheme():
    with pytest.raises(ValidationError, match="missing 'http://' or 'https://'"):
        Settings(ollama_host="127.0.0.1:11434")


def test_accepts_valid_ollama_host():
    settings = Settings(ollama_host="http://127.0.0.1:11434")
    assert settings.ollama_host == "http://127.0.0.1:11434"
