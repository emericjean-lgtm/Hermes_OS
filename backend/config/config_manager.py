"""Configuration Manager for Hermes OS (HOS-062).

Loads, validates, and merges configuration from profiles, env vars, and
runtime overrides. Supports 6 deployment profiles.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .config_models import (
    DeploymentProfile,
    HermesConfig,
)


class ConfigManager:
    """Central configuration manager for Hermes OS."""

    _instance: ConfigManager | None = None
    _lock = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> ConfigManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: str | None = None) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._config_path = config_path or os.environ.get(
            "HERMES_CONFIG", "backend/config/profiles/default.json"
        )
        self._config: HermesConfig = self._load_config()
        self._override_env()
        self._config.validate()
        self._lock = threading.RLock()

    # ── Public API ──

    @property
    def config(self) -> HermesConfig:
        return self._config

    def get(self) -> HermesConfig:
        with self._lock:
            return self._config

    def reload(self) -> HermesConfig:
        with self._lock:
            self._config = self._load_config()
            self._override_env()
            self._config.validate()
        return self._config

    def switch_profile(self, profile: DeploymentProfile) -> HermesConfig:
        profile_path = Path(self._config_path).parent / f"{profile.value}.json"
        if profile_path.exists():
            self._config_path = str(profile_path)
        return self.reload()

    def to_dict(self) -> dict[str, Any]:
        return self._config.to_dict()

    def validate_current(self) -> list[str]:
        return self._config.validate()

    # ── Private ──

    def _load_config(self) -> HermesConfig:
        path = self._resolve_config_path()
        if path and path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                return self._merge_config(data)
            except (json.JSONDecodeError, OSError):
                pass
        return self._default_config()

    def _resolve_config_path(self) -> Path | None:
        candidates = [
            Path(self._config_path),
            Path("config.json"),
            Path("hermes_config.json"),
            Path("backend/config/profiles/default.json"),
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _default_config(self) -> HermesConfig:
        return HermesConfig()

    def _merge_config(self, data: dict[str, Any]) -> HermesConfig:
        base = HermesConfig()

        profile = data.get("profile", "")
        if profile:
            try:
                base.profile = DeploymentProfile(profile)
            except ValueError:
                pass

        if "database" in data:
            db = data["database"]
            for k, v in db.items():
                if hasattr(base.database, k):
                    setattr(base.database, k, v)
        if "redis" in data:
            rd = data["redis"]
            for k, v in rd.items():
                if hasattr(base.redis, k):
                    setattr(base.redis, k, v)
        if "vector" in data:
            vc = data["vector"]
            for k, v in vc.items():
                if hasattr(base.vector, k):
                    setattr(base.vector, k, v)
        if "security" in data:
            sc = data["security"]
            for k, v in sc.items():
                if hasattr(base.security, k):
                    setattr(base.security, k, v)
        if "monitoring" in data:
            mc = data["monitoring"]
            for k, v in mc.items():
                if hasattr(base.monitoring, k):
                    setattr(base.monitoring, k, v)
        if "logging" in data:
            lc = data["logging"]
            for k, v in lc.items():
                if hasattr(base.logging, k):
                    setattr(base.logging, k, v)
        if "runtime" in data:
            rc = data["runtime"]
            for k, v in rc.items():
                if hasattr(base.runtime, k):
                    setattr(base.runtime, k, v)

        for key in ("api_host", "api_port", "frontend_url", "cors_origins",
                     "workspace_dir", "data_dir", "debug", "version"):
            if key in data:
                setattr(base, key, data[key])

        return base

    def _override_env(self) -> None:
        mapping: dict[str, tuple[str, type]] = {
            "HERMES_DB_HOST": ("host", str),
            "HERMES_DB_PORT": ("port", int),
            "HERMES_DB_NAME": ("name", str),
            "HERMES_DB_USER": ("user", str),
            "HERMES_DB_PASSWORD": ("password", str),
            "HERMES_REDIS_HOST": ("host", str),
            "HERMES_REDIS_PORT": ("port", int),
            "HERMES_REDIS_PASSWORD": ("password", str),
            "HERMES_VECTOR_HOST": ("host", str),
            "HERMES_VECTOR_PORT": ("port", int),
            "HERMES_JWT_SECRET": ("jwt_secret", str),
            "HERMES_LOG_LEVEL": ("level", str),
            "HERMES_API_PORT": ("api_port", int),
            "HERMES_API_HOST": ("api_host", str),
            "HERMES_FRONTEND_URL": ("frontend_url", str),
            "HERMES_WORKSPACE_DIR": ("workspace_dir", str),
            "HERMES_DATA_DIR": ("data_dir", str),
            "HERMES_DEFAULT_MODEL": ("default_model", str),
            "HERMES_GPU_ENABLED": ("enable_gpu", bool),
            "HERMES_MEMORY_LIMIT": ("memory_limit_mb", int),
        }

        for env_key, (attr_name, attr_type) in mapping.items():
            val = os.environ.get(env_key)
            if val is not None:
                if attr_type == bool:
                    typed_val = val.lower() in ("true", "1", "yes")
                elif attr_type == int:
                    typed_val = int(val)
                else:
                    typed_val = val

                parts = attr_name.split(".", 1)
                if len(parts) == 1:
                    if hasattr(self._config, attr_name):
                        setattr(self._config, attr_name, typed_val)
                else:
                    obj_name, sub_attr = parts
                    obj = getattr(self._config, obj_name, None)
                    if obj and hasattr(obj, sub_attr):
                        setattr(obj, sub_attr, typed_val)


def get_config() -> HermesConfig:
    """Convenience function to get the global config singleton."""
    return ConfigManager().get()
