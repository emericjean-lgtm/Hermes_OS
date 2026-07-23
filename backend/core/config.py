"""Central configuration loading: .env via pydantic-settings, plus the
models.yaml / agents.yaml catalogues. Nothing else in the codebase should
read os.environ or parse these YAML files directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_keep_alive: str = "10m"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    secret_key: str = "change_me_with_a_random_256bit_key"

    chroma_path: str = "./data/db/chroma"
    sqlite_path: str = "./data/db/hermes.db"

    allowed_paths: str = ""
    max_file_size_mb: int = 50

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    gpu_vram_total_gb: float = 16.0
    gpu_alert_temp_c: float = 85.0
    gpu_critical_temp_c: float = 90.0
    gpu_vram_warning_pct: float = 85.0

    skill_auto_validate_threshold: float = 0.95
    skill_min_confidence: float = 0.30
    reflection_enabled: bool = False
    ebbinghaus_decay_enabled: bool = False

    models_config_path: str = "./config/models.yaml"
    agents_config_path: str = "./config/agents.yaml"

    @property
    def allowed_paths_list(self) -> list[str]:
        return [p.strip() for p in self.allowed_paths.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _load_yaml(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {file_path}. "
            "Check MODELS_CONFIG_PATH / AGENTS_CONFIG_PATH in your .env."
        )
    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache
def load_models_config() -> dict[str, Any]:
    return _load_yaml(get_settings().models_config_path)


@lru_cache
def load_agents_config() -> dict[str, Any]:
    return _load_yaml(get_settings().agents_config_path)
