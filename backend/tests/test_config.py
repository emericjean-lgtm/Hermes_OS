from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.config import Settings


def test_rejects_empty_ollama_api_url():
    with pytest.raises(ValidationError, match="OLLAMA_API_URL is empty"):
        Settings(ollama_api_url="")


def test_rejects_ollama_api_url_without_scheme():
    with pytest.raises(ValidationError, match="missing 'http://' or 'https://'"):
        Settings(ollama_api_url="127.0.0.1:11434")


def test_accepts_valid_ollama_api_url():
    settings = Settings(ollama_api_url="http://127.0.0.1:11434")
    assert settings.ollama_api_url == "http://127.0.0.1:11434"
