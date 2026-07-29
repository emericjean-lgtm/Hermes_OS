"""Environment variable loader for Hermes OS (HOS-062).

Loads .env files and validates required environment variables
for each deployment profile.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .config_models import DeploymentProfile

REQUIRED_VARS: dict[DeploymentProfile, list[str]] = {
    DeploymentProfile.DOCKER: [
        "HERMES_DB_PASSWORD",
        "HERMES_JWT_SECRET",
    ],
    DeploymentProfile.SERVER: [
        "HERMES_DB_PASSWORD",
        "HERMES_JWT_SECRET",
        "HERMES_DB_HOST",
        "HERMES_DB_USER",
    ],
    DeploymentProfile.CLOUD_GPU: [
        "HERMES_DB_PASSWORD",
        "HERMES_JWT_SECRET",
        "HERMES_DB_HOST",
        "HERMES_DB_USER",
    ],
    DeploymentProfile.LOCAL_GPU: [],
    DeploymentProfile.CPU_ONLY: [],
    DeploymentProfile.WSL: [],
}

OPTIONAL_VARS: dict[DeploymentProfile, list[str]] = {
    DeploymentProfile.DOCKER: [
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
        "HERMES_DEFAULT_MODEL",
        "HERMES_GPU_ENABLED",
        "HERMES_REDIS_PASSWORD",
    ],
    DeploymentProfile.SERVER: [
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
        "HERMES_REDIS_PASSWORD",
        "HERMES_VECTOR_HOST",
        "HERMES_VECTOR_PORT",
        "HERMES_MEMORY_LIMIT",
        "HERMES_FRONTEND_URL",
    ],
    DeploymentProfile.LOCAL_GPU: [
        "HERMES_DEFAULT_MODEL",
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
    ],
    DeploymentProfile.CPU_ONLY: [
        "HERMES_DEFAULT_MODEL",
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
    ],
    DeploymentProfile.WSL: [
        "HERMES_DEFAULT_MODEL",
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
    ],
    DeploymentProfile.CLOUD_GPU: [
        "HERMES_API_PORT",
        "HERMES_LOG_LEVEL",
        "HERMES_DEFAULT_MODEL",
        "HERMES_VECTOR_HOST",
        "HERMES_VECTOR_PORT",
        "HERMES_MEMORY_LIMIT",
        "HERMES_FRONTEND_URL",
    ],
}


class EnvironmentLoader:
    """Loads and validates environment configuration."""

    def __init__(self, env_file: str | None = None):
        self._env_file = env_file or self._find_env_file()
        self._loaded: dict[str, str] = {}
        self._errors: list[str] = []
        self._warnings: list[str] = []

    # ── Public API ──

    def load(self, profile: DeploymentProfile | None = None) -> dict[str, str]:
        """Load environment from file and validate for profile."""
        self._loaded = {}
        self._errors = []
        self._warnings = []

        self._load_dotenv()
        self._collect_current_env()

        if profile:
            self._validate(profile)

        return self._loaded

    def get_errors(self) -> list[str]:
        return self._errors

    def get_warnings(self) -> list[str]:
        return self._warnings

    def is_valid(self, profile: DeploymentProfile) -> bool:
        self.load(profile)
        return len(self._errors) == 0

    def get_missing_required(self, profile: DeploymentProfile) -> list[str]:
        self.load(profile)
        return self._errors

    # ── Private ──

    def _find_env_file(self) -> str | None:
        candidates = [".env", ".env.production", ".env.local", "config/.env"]
        for c in candidates:
            if Path(c).exists():
                return c
        return None

    def _load_dotenv(self) -> None:
        if not self._env_file or not Path(self._env_file).exists():
            return
        try:
            with open(self._env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    match = re.match(r'^\s*export\s+([^=]+)=(.*)$', line)
                    if match:
                        key, val = match.group(1), match.group(2).strip("\"'")
                        os.environ.setdefault(key, val)
                        self._loaded[key] = val
                    elif "=" in line:
                        key, val = line.split("=", 1)
                        key, val = key.strip(), val.strip("\"'")
                        os.environ.setdefault(key, val)
                        self._loaded[key] = val
        except OSError as e:
            self._warnings.append(f"Could not read env file {self._env_file}: {e}")

    def _collect_current_env(self) -> None:
        for key, val in os.environ.items():
            if key.startswith("HERMES_"):
                self._loaded[key] = val

    def _validate(self, profile: DeploymentProfile) -> None:
        required = REQUIRED_VARS.get(profile, [])
        for var in required:
            if var not in os.environ or not os.environ[var]:
                self._errors.append(f"Missing required env var: {var}")

        optional = OPTIONAL_VARS.get(profile, [])
        for var in optional:
            if var not in os.environ:
                self._warnings.append(f"Optional env var not set: {var}")
