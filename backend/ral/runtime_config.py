"""Runtime Abstraction Layer — runtime configuration (HOS-005).

This module defines the :class:`RuntimeConfig` dataclass used to configure
a concrete runtime adapter. It intentionally depends on **no** module
from :mod:`backend.core` or any global settings system, so the RAL
contracts stay decoupled from FastAPI / pydantic-settings.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    """Immutable configuration parameters for a concrete runtime adapter.

    Attributes:
        model: Model identifier to use (e.g. ``"qwen3.5:9b"``).
        endpoint: URL of the inference server (e.g. ``"http://127.0.0.1:11434"``).
        timeout_seconds: Maximum time in seconds to wait for a response.
    """

    model: str
    endpoint: str
    timeout_seconds: int = 120
