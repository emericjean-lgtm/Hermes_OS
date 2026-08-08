"""Tests for the Model Benchmark & Discovery Engine (HOS-040)."""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from backend.runtime.discovery.benchmark_engine import BenchmarkEngine
from backend.runtime.discovery.compatibility_analyzer import CompatibilityAnalyzer
from backend.runtime.discovery.cron_scheduler import CronScheduler, TaskType
from backend.runtime.discovery.discovery_engine import (
    DiscoveryEngine,
    HuggingFaceConnector,
    OllamaConnector,
)
from backend.runtime.discovery.discovery_models import (
    BenchmarkProfile,
    DiscoverySource,
    ModelInfo,
    ModelStatus,
    Quantization,
)
from backend.runtime.discovery.model_registry import ModelRegistry

# HOS-072: OllamaConnector now queries a real Ollama /api/tags instead of a
# hardcoded catalogue — tests inject a fake transport rather than requiring
# a live server, the same pattern used for the real chat/benchmark clients
# elsewhere in this codebase.
_FAKE_TAGS_RESPONSE = {
    "models": [
        {
            "name": "qwen3.5:9b",
            "size": 5_721_139_200,
            "details": {"family": "qwen3", "parameter_size": "9.3B",
                        "quantization_level": "Q4_K_M"},
        },
        {
            "name": "nomic-embed-text",
            "size": 274_302_450,
            "details": {"family": "nomic-bert", "parameter_size": "137M",
                        "quantization_level": "F16"},
        },
    ]
}


def _fake_ollama_client(response: dict | None = None) -> httpx.Client:
    payload = response if response is not None else _FAKE_TAGS_RESPONSE

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(base_url="http://fake-ollama", transport=httpx.MockTransport(handler))


def _unreachable_ollama_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    return httpx.Client(base_url="http://fake-ollama", transport=httpx.MockTransport(handler))


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry(max_models=500)


@pytest.fixture
def compatibility() -> CompatibilityAnalyzer:
    return CompatibilityAnalyzer()


@pytest.fixture
def discovery(registry: ModelRegistry) -> DiscoveryEngine:
    return DiscoveryEngine(registry=registry)


# ─── 1. Model Registry Tests ───────────────────────────────


class TestModelRegistry:
    def test_register_and_get(self, registry: ModelRegistry):
        model = ModelInfo(name="qwen3:14b", provider="ollama", parameter_count_b=14.0)
        registry.register(model)
        assert registry.count() == 1
        assert registry.get(model.model_id) is not None
        assert registry.get_by_name("qwen3:14b") is not None

    def test_list_all(self, registry: ModelRegistry):
        registry.register(ModelInfo(name="a"))
        registry.register(ModelInfo(name="b"))
        assert len(registry.list_all()) == 2

    def test_list_by_status(self, registry: ModelRegistry):
        m = ModelInfo(name="test", status=ModelStatus.COMPATIBLE)
        registry.register(m)
        assert len(registry.list_all(ModelStatus.COMPATIBLE)) == 1
        assert len(registry.list_all(ModelStatus.BENCHMARKED)) == 0

    def test_update_status(self, registry: ModelRegistry):
        m = ModelInfo(name="test")
        registry.register(m)
        assert registry.update_status(m.model_id, ModelStatus.COMPATIBLE)
        assert registry.get(m.model_id).status == ModelStatus.COMPATIBLE

    def test_benchmarks(self, registry: ModelRegistry):
        from backend.runtime.discovery.discovery_models import BenchmarkResult
        bm = BenchmarkResult(model_name="test", profile=BenchmarkProfile.GENERAL_CHAT)
        registry.add_benchmark(bm)
        assert len(registry.get_benchmarks("test")) == 1
        assert len(registry.get_all_benchmarks()) == 1

    def test_stats(self, registry: ModelRegistry):
        registry.register(ModelInfo(name="a", source=DiscoverySource.OLLAMA))
        registry.register(ModelInfo(name="b", source=DiscoverySource.HUGGINGFACE))
        stats = registry.get_stats()
        assert stats["total_models"] == 2
        assert "ollama" in stats["by_source"]


# ─── 2. Compatibility Analyzer Tests ───────────────────────


class TestCompatibilityAnalyzer:
    def test_compatible_model(self, compatibility: CompatibilityAnalyzer):
        model = ModelInfo(
            name="qwen3:14b",
            architecture="qwen3",
            parameter_count_b=14.0,
            quantization=Quantization.Q4_K_M,
        )
        report = compatibility.analyze(model, vram_total=16 * 1024**3)
        # 14B * Q4_K_M (~0.30) = 4.2 GB < 16 GB
        assert report.compatible
        assert report.rocm_supported

    def test_incompatible_too_large(self, compatibility: CompatibilityAnalyzer):
        model = ModelInfo(
            name="deepseek-r1:32b",
            architecture="deepseek",
            parameter_count_b=32.0,
            quantization=Quantization.Q4_K_M,
        )
        report = compatibility.analyze(model, vram_total=4 * 1024**3)
        # 32B * 0.30 = 9.6 GB > 4 GB
        assert not report.compatible
        assert len(report.issues) > 0

    def test_rocm_supported_architectures(self, compatibility: CompatibilityAnalyzer):
        for arch in ["llama", "qwen3", "mistral", "gemma", "deepseek", "phi"]:
            model = ModelInfo(name=f"test", architecture=arch, parameter_count_b=1.0)
            report = compatibility.analyze(model)
            assert report.rocm_supported, f"{arch} should be ROCm-supported"

    def test_unknown_architecture(self, compatibility: CompatibilityAnalyzer):
        model = ModelInfo(name="unknown-model", architecture="exotic-arch", parameter_count_b=7.0)
        report = compatibility.analyze(model)
        assert not report.rocm_supported


# ─── 3. Discovery Engine Tests ─────────────────────────────


class TestDiscoveryEngine:
    def test_discover_from_ollama(self, discovery: DiscoveryEngine):
        discovery.register_connector(OllamaConnector(client=_fake_ollama_client()))
        run = discovery.discover(sources=[DiscoverySource.OLLAMA])
        assert run.models_found > 0
        assert run.new_models > 0
        assert any(m.source == DiscoverySource.OLLAMA for m in run.models)

    def test_discover_from_huggingface(self, discovery: DiscoveryEngine):
        run = discovery.discover(sources=[DiscoverySource.HUGGINGFACE])
        assert run.models_found > 0
        assert any(m.source == DiscoverySource.HUGGINGFACE for m in run.models)

    def test_discover_all(self, discovery: DiscoveryEngine):
        discovery.register_connector(OllamaConnector(client=_fake_ollama_client()))
        run = discovery.discover()
        assert run.models_found > 0
        assert len(discovery.get_discovery_runs()) == 1

    def test_duplicate_detection(self, discovery: DiscoveryEngine):
        discovery.register_connector(OllamaConnector(client=_fake_ollama_client()))
        discovery.discover(sources=[DiscoverySource.OLLAMA])
        run2 = discovery.discover(sources=[DiscoverySource.OLLAMA])
        assert run2.new_models == 0

    def test_discover_from_ollama_unreachable_returns_empty_not_fabricated(
        self, discovery: DiscoveryEngine,
    ):
        """HOS-072: an unreachable Ollama must report zero real models,
        never the old hardcoded catalogue standing in for them."""
        discovery.register_connector(OllamaConnector(client=_unreachable_ollama_client()))
        run = discovery.discover(sources=[DiscoverySource.OLLAMA])
        assert run.models_found == 0
        assert run.models == []

    def test_connectors(self, discovery: DiscoveryEngine):
        connectors = discovery.get_connectors()
        assert "ollama" in connectors
        assert "huggingface" in connectors


# ─── 4. Connector Tests ────────────────────────────────────


class TestConnectors:
    def test_ollama_connector(self):
        connector = OllamaConnector(client=_fake_ollama_client())
        models = connector.discover()
        assert len(models) == 2
        assert all(m.source == DiscoverySource.OLLAMA for m in models)

    def test_ollama_connector_reads_real_fields_not_a_guess(self):
        connector = OllamaConnector(client=_fake_ollama_client())
        models = {m.name: m for m in connector.discover()}
        qwen = models["qwen3.5:9b"]
        assert qwen.architecture == "qwen3"
        assert qwen.parameter_count_b == 9.3
        assert qwen.quantization == Quantization.Q4_K_M
        assert qwen.size_bytes == 5_721_139_200

    def test_ollama_connector_unreachable_returns_empty(self):
        connector = OllamaConnector(client=_unreachable_ollama_client())
        assert connector.discover() == []

    def test_huggingface_connector(self):
        connector = HuggingFaceConnector()
        models = connector.discover()
        assert len(models) >= 1
        assert all(m.source == DiscoverySource.HUGGINGFACE for m in models)


# ─── 5. Benchmark Engine Tests ─────────────────────────────


class TestBenchmarkEngine:
    def test_benchmark_model(self, registry: ModelRegistry):
        def mock_execute(model: str, prompt: str) -> dict:
            return {"tokens": 150, "duration_ms": 500.0, "ttft_ms": 80.0, "vram_bytes": 8*1024**3, "ram_bytes": 16*1024**3}

        engine = BenchmarkEngine(registry=registry, execute_prompt=mock_execute)
        model = ModelInfo(name="qwen3:14b", parameter_count_b=14.0)
        result = engine.benchmark_model(model, profile=BenchmarkProfile.CODING)
        assert result.success
        assert result.tokens_per_second > 0
        assert result.time_to_first_token_ms > 0
        assert result.profile == BenchmarkProfile.CODING

    def test_benchmark_all(self, registry: ModelRegistry):
        def mock_execute(model: str, prompt: str) -> dict:
            return {"tokens": 100, "duration_ms": 400.0, "ttft_ms": 50.0, "vram_bytes": 4*1024**3, "ram_bytes": 8*1024**3}

        engine = BenchmarkEngine(registry=registry, execute_prompt=mock_execute)
        models = [ModelInfo(name="test-model", parameter_count_b=7.0)]
        results = engine.benchmark_all(models)
        assert len(results) == len(BenchmarkProfile)

    def test_benchmarks_stored(self, registry: ModelRegistry):
        def mock_execute(model: str, prompt: str) -> dict:
            return {"tokens": 100, "duration_ms": 300.0, "ttft_ms": 60.0, "vram_bytes": 0, "ram_bytes": 0}

        engine = BenchmarkEngine(registry=registry, execute_prompt=mock_execute)
        model = ModelInfo(name="test", parameter_count_b=7.0)
        engine.benchmark_model(model)
        bms = registry.get_benchmarks("test")
        assert len(bms) >= 1


# ─── 6. Cron Scheduler Tests ──────────────────────────────


class TestCronScheduler:
    def test_schedule_and_start(self):
        scheduler = CronScheduler()
        results: list[str] = []

        def task() -> None:
            results.append("ran")

        scheduler.schedule(TaskType.DISCOVERY, interval_seconds=0.1, callback=task, name="test")
        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()
        assert len(results) >= 1

    def test_status(self):
        scheduler = CronScheduler()
        scheduler.schedule(TaskType.DISCOVERY, interval_seconds=60.0, callback=lambda: None, name="discovery")
        status = scheduler.get_status()
        assert status["tasks_count"] == 1
        assert status["running"] is False


# ─── 7. Thread Safety ──────────────────────────────────────


class TestDiscoveryThreadSafety:
    def test_concurrent_registry_access(self, registry: ModelRegistry):
        errors: list[Exception] = []

        def writer() -> None:
            for i in range(50):
                try:
                    registry.register(ModelInfo(name=f"model-{i}"))
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(100):
                try:
                    registry.list_all()
                    registry.get_stats()
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert not errors

    def test_concurrent_discovery(self, discovery: DiscoveryEngine):
        errors: list[Exception] = []

        def worker() -> None:
            try:
                discovery.discover(sources=[DiscoverySource.OLLAMA])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
