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

def _parse_param_size(raw: object) -> float:
    """Ollama reports parameter size as a string like ``"9.3B"``/``"770M"``
    in /api/tags' ``details.parameter_size`` — parse it into billions, or
    0.0 if absent/unparseable (an honest "not known", not a guess)."""
    if not isinstance(raw, str) or not raw:
        return 0.0
    text = raw.strip().upper()
    try:
        if text.endswith("B"):
            return float(text[:-1])
        if text.endswith("M"):
            return float(text[:-1]) / 1000.0
        return float(text)
    except ValueError:
        return 0.0


def _map_quantization(raw: object) -> Quantization:
    """Ollama's ``details.quantization_level`` (e.g. "Q4_K_M") maps
    directly onto most of our own Quantization values; anything else
    (or absent) stays UNKNOWN rather than a guessed default."""
    if not isinstance(raw, str):
        return Quantization.UNKNOWN
    try:
        return Quantization(raw.strip().lower())
    except ValueError:
        return Quantization.UNKNOWN


class OllamaConnector(DiscoveryConnector):
    """Discovers models actually installed on the configured Ollama server.

    HOS-072 audit: this used to return a hardcoded "simplified catalogue"
    of 12 generic model names with no relationship to what was actually
    installed on any given deployment — this project's own real models
    (qwen3:1.7b/qwen3:4b/qwen3.5:9b/gemma4:12b/nomic-embed-text, see
    config/models.yaml) never appeared in it, while it invented several
    that were never installed anywhere (qwen3:8b, deepseek-r1:32b,
    phi4:14b...). "Discovered" now means Ollama's own real ``/api/tags``
    said so. Returns an empty list — never fabricated entries — if Ollama
    can't be reached, matching the "never fabricate" rule the rest of the
    real inference/benchmark paths already follow.
    """

    source = DiscoverySource.OLLAMA

    def __init__(self, client: object | None = None) -> None:
        """``client`` (an ``httpx.Client``): injected for hermetic tests
        (a real Ollama server is never reachable in CI); None builds one
        from the configured endpoint on each call, same DI pattern as
        BenchmarkScheduler's ``chat``/``cloud_chat``."""
        self._client = client

    def discover(self) -> list[ModelInfo]:
        import httpx

        client = self._client
        owns_client = client is None
        if owns_client:
            from backend.core.config import get_settings

            settings = get_settings()
            client = httpx.Client(
                base_url=settings.ollama_api_url.rstrip("/"), timeout=5.0,
            )
        try:
            response = client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []
        finally:
            if owns_client:
                client.close()

        models: list[ModelInfo] = []
        for entry in payload.get("models") or []:
            name = str(entry.get("name") or entry.get("model") or "")
            if not name:
                continue
            details = entry.get("details") or {}
            models.append(ModelInfo(
                name=name,
                provider="ollama",
                architecture=str(details.get("family") or ""),
                parameter_count_b=_parse_param_size(details.get("parameter_size")),
                quantization=_map_quantization(details.get("quantization_level")),
                size_bytes=int(entry.get("size") or 0),
                source=DiscoverySource.OLLAMA,
                source_url=f"https://ollama.com/library/{name.split(':')[0]}",
                tags=[],
                status=ModelStatus.DISCOVERED,
            ))
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
