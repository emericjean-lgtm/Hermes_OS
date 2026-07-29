"""Tests for HOS-052B — KTransformers Hermes Integration Layer."""

from __future__ import annotations

import threading

import pytest

from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTInferenceRequest,
    KTModelInfo,
    KTModelStatus,
    KTQuantization,
)
from backend.runtime.ktransformers.hermes_adapter import (
    KTKernelWrapper,
    get_kernel_wrapper,
    is_kernel_available,
    cpu_variant,
)
from backend.runtime.ktransformers.kt_runtime import KTRuntime
from backend.runtime.ktransformers.integrations.orchestrator import (
    KTOchestratorIntegration,
    KTRuntimeCandidate,
)
from backend.runtime.ktransformers.integrations.discovery import (
    KTDiscoveryIntegration,
    KTBenchmarkIntegration,
)
from backend.runtime.ktransformers.integrations.resources import (
    KTResourceIntegration,
    KTEventBusBridge,
)


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def kernel():
    return get_kernel_wrapper()


@pytest.fixture
def runtime():
    return KTRuntime()


@pytest.fixture
def sample_model():
    return KTModelInfo(
        name="test-model-7b",
        path="/models/test.gguf",
        quantization=KTQuantization.Q4_K_M,
        size_gb=4.0,
        size_params="7B",
        architecture="llama",
        backend=KTBackend.ROCM,
        tags=["chat", "coding"],
    )


# ── Hermes Adapter ────────────────────────────────────

class TestHermesAdapter:
    def test_kernel_available(self):
        """Kernel status is correctly reported."""
        available = is_kernel_available()
        assert isinstance(available, bool)

    def test_cpu_variant(self):
        """CPU variant is a string."""
        variant = cpu_variant()
        assert isinstance(variant, str)
        assert len(variant) > 0

    def test_wrapper_load_simulated(self, kernel: KTKernelWrapper, sample_model: KTModelInfo):
        """Simulated load works (kt-kernel not required for tests)."""
        success = kernel.load_model(sample_model, KTBackend.ROCM)
        assert success
        assert kernel.is_loaded(sample_model.id)

    def test_wrapper_unload(self, kernel: KTKernelWrapper, sample_model: KTModelInfo):
        """Unload removes model."""
        kernel.load_model(sample_model, KTBackend.ROCM)
        assert kernel.unload_model(sample_model.id)
        assert not kernel.is_loaded(sample_model.id)

    def test_wrapper_infer_simulated(self, kernel: KTKernelWrapper, sample_model: KTModelInfo):
        """Simulated inference returns results."""
        kernel.load_model(sample_model)
        req = KTInferenceRequest(model_id=sample_model.id, prompt="Hello", max_tokens=50)
        result = kernel.infer(req)
        assert result.tokens_generated > 0
        assert len(result.text) > 0

    def test_wrapper_status(self, kernel: KTKernelWrapper):
        """Status reports correctly."""
        st = kernel.status()
        assert "kernel_available" in st
        assert "cpu_variant" in st
        assert "mode" in st

    def test_singleton(self):
        """get_kernel_wrapper returns same instance."""
        w1 = get_kernel_wrapper()
        w2 = get_kernel_wrapper()
        assert w1 is w2


# ── Orchestrator Integration ──────────────────────────

class TestOrchestratorIntegration:
    def test_as_candidate(self):
        """Produces a valid orchestrator candidate."""
        orch = KTOchestratorIntegration()
        cand = orch.as_candidate()
        assert isinstance(cand, KTRuntimeCandidate)
        assert cand.name == "ktransformers"
        assert cand.type == "LOCAL_INFERENCE"
        assert isinstance(cand.capabilities, list)
        assert "CHAT" in cand.capabilities

    def test_can_handle_task(self):
        """KT can handle MoE and general tasks."""
        orch = KTOchestratorIntegration()
        assert orch.can_handle_task("coding", "deepseek-v3-moe")
        assert orch.can_handle_task("chat", "qwen3-moe")

    def test_suitability_score(self):
        """Scores are in valid range."""
        orch = KTOchestratorIntegration()
        score = orch.suitability_score("coding", "deepseek-moe")
        assert 0 <= score <= 100
        # MoE tasks score higher
        score_chat = orch.suitability_score("chat", "llama-7b")
        assert score >= score_chat  # MoE has bonus

    def test_execute(self, runtime: KTRuntime, sample_model: KTModelInfo):
        """Execute through orchestrator."""
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        result = runtime.orchestrator.execute(sample_model.id, "Hello", max_tokens=32)
        assert result.tokens_generated > 0


# ── Discovery Integration ─────────────────────────────

class TestDiscoveryIntegration:
    def test_discover_models(self, runtime: KTRuntime):
        """Discovery finds known KT-compatible models."""
        discovered = KTDiscoveryIntegration.discover_models(None)
        assert len(discovered) > 0
        # Check known models are present
        names = [m.name for m in discovered]
        assert "DeepSeek-V3" in names
        assert "Qwen3-30B-A3B" in names

    def test_discover_and_register(self, runtime: KTRuntime):
        """Discovery registers models in runtime."""
        discovered = runtime.discover_and_register()
        assert len(discovered) > 0
        assert runtime.list_models()

    def test_discovered_models_have_tags(self):
        """Discovered models are tagged correctly."""
        discovered = KTDiscoveryIntegration.discover_models(None)
        for m in discovered:
            assert m.discovered_from == "huggingface"
            assert "moe" in m.tags or m.architecture in ["phi", "llama", "mixtral"]


# ── Benchmark Integration ─────────────────────────────

class TestBenchmarkIntegration:
    def test_benchmark_model(self, runtime: KTRuntime, sample_model: KTModelInfo):
        """Benchmarking produces results."""
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        results = runtime.benchmark.benchmark_model(sample_model, profiles=["chat", "coding"])
        assert len(results) > 0
        for r in results:
            assert r.tokens_per_second > 0
            assert r.success

    def test_benchmark_profiles(self):
        """All benchmark profiles are defined."""
        bench = KTBenchmarkIntegration()
        profiles = list(bench.BENCHMARK_PROFILES.keys())
        assert "coding" in profiles
        assert "reasoning" in profiles
        assert "general_chat" in profiles

    def test_best_for_task(self, runtime: KTRuntime, sample_model: KTModelInfo):
        """Best model per task type is found."""
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        runtime.benchmark.benchmark_model(sample_model, profiles=["chat", "coding"])
        best = runtime.benchmark.best_for_task("coding")
        if best:
            assert best.model_id == sample_model.id

    def test_clear_results(self):
        """Clear removes all benchmark results."""
        bench = KTBenchmarkIntegration()
        bench._results = [{"dummy": True}]  # type: ignore
        assert bench.clear() > 0
        assert len(bench.get_results()) == 0


# ── Resource Integration ──────────────────────────────

class TestResourceIntegration:
    def test_update_from_snapshot(self):
        """Resource data updates correctly."""
        res = KTResourceIntegration()
        res.update_from_resource_manager({
            "vram_total_gb": 16.0,
            "vram_used_gb": 4.0,
            "ram_total_gb": 32.0,
            "ram_used_gb": 8.0,
        })
        snap = res.snapshot()
        assert snap["vram_free_gb"] == 12.0
        assert snap["ram_free_gb"] == 24.0

    def test_free_never_negative(self):
        """Free VRAM/RAM is never negative."""
        res = KTResourceIntegration()
        res.update_from_resource_manager({
            "vram_total_gb": 8.0,
            "vram_used_gb": 20.0,  # More used than total
        })
        assert res.vram_free_gb() == 0.0


# ── Event Bus Integration ─────────────────────────────

class TestEventBusBridge:
    def test_publish_sends_event(self):
        """Events are published and counted."""
        received = []

        def capture(event_type, payload):
            received.append((event_type, payload))

        bridge = KTEventBusBridge(publish_fn=capture)
        bridge.model_loaded("m1", "test-model", "rocm")
        assert bridge.event_count == 1
        assert len(received) == 1
        assert received[0][0] == "ktransformers.model_loaded"

    def test_all_events_publish(self):
        """All convenience methods work."""
        received = []
        bridge = KTEventBusBridge(publish_fn=lambda t, p: received.append(t))

        bridge.model_discovered("m", "hf")
        bridge.model_loaded("m1", "m", "rocm")
        bridge.model_unloaded("m1")
        bridge.fallback_triggered("m1", "vram", "cpu")

        expected = [
            "ktransformers.model_discovered",
            "ktransformers.model_loaded",
            "ktransformers.model_unloaded",
            "ktransformers.fallback_triggered",
        ]
        for e in expected:
            assert e in received

    def test_no_publisher_no_error(self):
        """Bridge works without a publisher."""
        bridge = KTEventBusBridge(publish_fn=None)
        bridge.model_loaded("m1", "test", "rocm")
        assert bridge.event_count == 1

    def test_benchmark_event(self):
        """Benchmark completion event is published."""
        received = []
        bridge = KTEventBusBridge(publish_fn=lambda t, p: received.append(t))
        bridge.benchmark_completed("deepseek", "coding", 45.2)
        assert "ktransformers.benchmark_completed" in received

    def test_inference_event(self):
        """Inference completion event is published."""
        from backend.runtime.ktransformers.kt_models import KTInferenceResult
        result = KTInferenceResult(
            model_id="m1", tokens_generated=128,
            tokens_per_second=50.0, duration_ms=2560.0,
        )
        received = []
        bridge = KTEventBusBridge(publish_fn=lambda t, p: received.append(t))
        bridge.inference_completed(result)
        assert "ktransformers.inference_completed" in received


# ── Full Runtime Integration ──────────────────────────

class TestFullIntegration:
    def test_end_to_end(self, runtime: KTRuntime, sample_model: KTModelInfo):
        """Full pipeline: discover → register → load → infer → unload."""
        # Register
        runtime.register_model(sample_model)
        assert runtime.get_model(sample_model.id) is not None

        # Load
        assert runtime.load_model(sample_model.id)
        assert runtime.is_model_loaded(sample_model.id)

        # Infer
        req = KTInferenceRequest(model_id=sample_model.id, prompt="Test", max_tokens=64)
        result = runtime.infer(req)
        assert result.tokens_generated > 0

        # Optimize
        opt = runtime.optimize_for_task("7B", "coding")
        assert opt.score > 0

        # Unload
        assert runtime.unload_model(sample_model.id)
        assert not runtime.is_model_loaded(sample_model.id)

    def test_discover_benchmark_pipeline(self, runtime: KTRuntime):
        """Discover → register → benchmark pipeline."""
        # Discover and register
        discovered = runtime.discover_and_register()
        assert len(discovered) > 0

        # Load first model
        first = discovered[0]
        runtime.load_model(first.id)

        # Benchmark
        results = runtime.benchmark.benchmark_model(first, profiles=["chat"])
        assert len(results) == 1
        assert results[0].success

    def test_resource_aware_optimization(self, runtime: KTRuntime):
        """Optimization uses live resource data."""
        # Set resources
        runtime.resources.update_from_resource_manager({
            "vram_total_gb": 16.0, "vram_used_gb": 14.0,
            "ram_total_gb": 32.0, "ram_used_gb": 4.0,
        })
        # With only 2GB VRAM free, a 13B model should fallback
        opt = runtime.optimize_for_task("13B", "chat")
        assert opt.fallback_needed

    def test_orchestrator_events(self, runtime: KTRuntime, sample_model: KTModelInfo):
        """Loading/unloading triggers events."""
        runtime.register_model(sample_model)
        before = runtime.events.event_count

        runtime.load_model(sample_model.id)
        assert runtime.events.event_count > before

        runtime.unload_model(sample_model.id)
        assert runtime.events.event_count > before + 1


# ── Thread Safety ─────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_load(self, runtime: KTRuntime):
        """Concurrent model loading is safe."""
        models = []
        for i in range(10):
            m = KTModelInfo(name=f"concurrent-{i}", size_gb=1.0)
            runtime.register_model(m)
            models.append(m)

        def load_one(m):
            runtime.load_model(m.id)

        threads = [threading.Thread(target=load_one, args=(m,)) for m in models]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_concurrent_events(self):
        """Concurrent event publishing is safe."""
        bridge = KTEventBusBridge()
        errors = []

        def publish_many():
            try:
                for i in range(20):
                    bridge.model_loaded(f"m{i}", f"model-{i}", "rocm")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=publish_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert bridge.event_count == 100

    def test_concurrent_discovery(self, runtime: KTRuntime):
        """Concurrent discovery is safe."""
        errors = []

        def discover():
            try:
                KTDiscoveryIntegration.discover_models(None)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=discover) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
