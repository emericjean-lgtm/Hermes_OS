"""Discovery Engine for the Model Benchmark & Discovery Engine (HOS-040).

Discovers new models from multiple sources (HuggingFace, Ollama, GitHub, etc.)
Pluggable connector architecture for easy extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.runtime.discovery.compatibility_analyzer import CompatibilityAnalyzer
from backend.runtime.discovery.discovery_models import (
    DiscoveryRun,
    DiscoverySource,
    ModelInfo,
    ModelStatus,
    Quantization,
)
from backend.runtime.discovery.model_registry import ModelRegistry


# ── Connector Interface ────────────────────────────────────

class DiscoveryConnector(ABC):
    """Abstract connector for model discovery sources."""

    source: DiscoverySource

    @abstractmethod
    def discover(self) -> list[ModelInfo]:
        """Fetch available models from this source."""
        ...


# ── Concrete Connectors ────────────────────────────────────

class OllamaConnector(DiscoveryConnector):
    """Discovers models available via Ollama."""

    source = DiscoverySource.OLLAMA

    # Known Ollama models (simplified catalogue)
    _catalogue: list[dict] = [
        {"name": "qwen3:1.7b", "params": 1.7, "arch": "qwen3", "tags": ["chat", "fast"]},
        {"name": "qwen3:4b", "params": 4.0, "arch": "qwen3", "tags": ["chat"]},
        {"name": "qwen3:8b", "params": 8.0, "arch": "qwen3", "tags": ["chat", "balanced"]},
        {"name": "qwen3:14b", "params": 14.0, "arch": "qwen3", "tags": ["chat", "code"]},
        {"name": "qwen3-coder:30b", "params": 30.0, "arch": "qwen3", "tags": ["code", "heavy"]},
        {"name": "deepseek-r1:14b", "params": 14.0, "arch": "deepseek", "tags": ["reasoning"]},
        {"name": "deepseek-r1:32b", "params": 32.0, "arch": "deepseek", "tags": ["reasoning", "heavy"]},
        {"name": "gemma3:12b", "params": 12.0, "arch": "gemma", "tags": ["vision", "chat"]},
        {"name": "phi4:14b", "params": 14.0, "arch": "phi", "tags": ["security", "reasoning"]},
        {"name": "llama3.2:3b", "params": 3.2, "arch": "llama", "tags": ["chat", "fast"]},
        {"name": "nomic-embed-text", "params": 0.3, "arch": "embedding", "tags": ["embedding"]},
        {"name": "codellama:13b", "params": 13.0, "arch": "codegemma", "tags": ["code"]},
    ]

    def discover(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for entry in self._catalogue:
            model = ModelInfo(
                name=entry["name"],
                provider="ollama",
                architecture=entry["arch"],
                parameter_count_b=entry["params"],
                quantization=Quantization.Q4_K_M,
                size_bytes=int(entry["params"] * 0.3 * 1024**3),
                source=DiscoverySource.OLLAMA,
                source_url=f"https://ollama.com/library/{entry['name'].split(':')[0]}",
                tags=entry.get("tags", []),
                status=ModelStatus.DISCOVERED,
            )
            models.append(model)
        return models


class HuggingFaceConnector(DiscoveryConnector):
    """Discovers models from HuggingFace Hub."""

    source = DiscoverySource.HUGGINGFACE

    # Curated hot list
    _hot_list: list[dict] = [
        {"name": "microsoft/phi-4", "params": 14.0, "arch": "phi", "tags": ["security"]},
        {"name": "mistralai/Mistral-Nemo-12B", "params": 12.0, "arch": "mistral", "tags": ["chat"]},
        {"name": "meta-llama/Llama-3.1-8B", "params": 8.0, "arch": "llama", "tags": ["chat"]},
    ]

    def discover(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for entry in self._hot_list:
            model = ModelInfo(
                name=entry["name"],
                provider="huggingface",
                architecture=entry["arch"],
                parameter_count_b=entry["params"],
                quantization=Quantization.Q4_K_M,
                size_bytes=int(entry["params"] * 0.3 * 1024**3),
                source=DiscoverySource.HUGGINGFACE,
                source_url=f"https://huggingface.co/{entry['name']}",
                tags=entry.get("tags", []),
                status=ModelStatus.DISCOVERED,
            )
            models.append(model)
        return models


# ── Discovery Engine ───────────────────────────────────────

class DiscoveryEngine:
    """Orchestrates model discovery across multiple sources.

    Thread-safe. Extensible via connector registration.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        compatibility: Optional[CompatibilityAnalyzer] = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._registry = registry
        self._compatibility = compatibility or CompatibilityAnalyzer()
        self._on_event = on_event
        self._connectors: dict[DiscoverySource, DiscoveryConnector] = {}
        self._history: list[DiscoveryRun] = []

        # Register default connectors
        self.register_connector(OllamaConnector())
        self.register_connector(HuggingFaceConnector())

    def register_connector(self, connector: DiscoveryConnector) -> None:
        self._connectors[connector.source] = connector

    # ── Discovery ──────────────────────────────────────────

    def discover(self, sources: Optional[list[DiscoverySource]] = None) -> DiscoveryRun:
        """Run discovery across specified sources (or all)."""
        targets = sources or list(self._connectors.keys())
        run = DiscoveryRun(
            sources=targets,
            started_at=datetime.now(timezone.utc),
        )

        for source in targets:
            connector = self._connectors.get(source)
            if connector is None:
                continue

            try:
                models = connector.discover()
                new_count = 0
                for model in models:
                    existing = self._registry.get_by_name(model.name)
                    if existing is None:
                        self._registry.register(model)
                        new_count += 1
                        # Run compatibility check
                        report = self._compatibility.analyze(model)
                        if report.compatible:
                            self._registry.update_status(model.model_id, ModelStatus.COMPATIBLE)
                        else:
                            self._registry.update_status(model.model_id, ModelStatus.INCOMPATIBLE)
                    else:
                        model = existing

                run.models_found += len(models)
                run.new_models += new_count
                run.models.extend(models)

                if self._on_event and new_count > 0:
                    self._on_event(
                        "discovery.new_models_found",
                        {"source": source.value, "count": new_count},
                        severity="info",
                    )
            except Exception as e:
                if self._on_event:
                    self._on_event(
                        "discovery.error",
                        {"source": source.value, "error": str(e)},
                        severity="warning",
                    )

        run.completed_at = datetime.now(timezone.utc)
        self._history.append(run)
        if len(self._history) > 200:
            self._history = self._history[-200:]

        return run

    # ── Query ───────────────────────────────────────────────

    def get_discovery_runs(self, limit: int = 20) -> list[DiscoveryRun]:
        return self._history[-limit:]

    def get_connectors(self) -> list[str]:
        return [s.value for s in self._connectors.keys()]
