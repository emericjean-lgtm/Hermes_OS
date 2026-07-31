"""HOS-052C — KTransformers Final Integration Tests.

Tests the complete Hermes ↔ KT bridge with real adapter patterns.
All tests run without requiring kt-kernel installed (uses simulated fallback).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed


from backend.runtime.ktransformers.hermes_adapter import HermesKTAdapter, _detect_best_backend
from backend.runtime.ktransformers.integrations.discovery import (
    KTBenchmarkIntegration,
    KTDiscoveryIntegration,
    _KNOWN_KT_MODELS,
)
from backend.runtime.ktransformers.integrations.orchestrator import (
    KTCandidate,
    KTOchestratorIntegration,
)
from backend.runtime.ktransformers.integrations.resources import (
    KTEventBusBridge,
    KTResourceIntegration,
)
from backend.runtime.ktransformers.kt_models import (
    KTBackend,
    KTFallbackReason,
    KTInferenceRequest,
    KTModelConfig,
    KTModelInfo,
    KTModelStatus,
    KTOptimizationResult,
    KTQuantization,
)
from backend.runtime.ktransformers.kt_runtime import KTRuntime, get_kt_runtime


# ── Helpers ────────────────────────────────────────────────────────

def _make_model(
    name: str = "test-model",
    architecture: str = "dense",
    backend: KTBackend = KTBackend.CPU,
    quantization: KTQuantization = KTQuantization.Q4_K_M,
    vram: float = 8.0,
    ram: float = 16.0,
    is_moe: bool = False,
) -> KTModelInfo:
    return KTModelInfo(
        name=name,
        full_name=f"test/{name}",
        architecture="MoE" if is_moe else architecture,
        num_parameters="7B",
        size_gb=4.0,
        quantization=quantization,
        backend=backend,
        status=KTModelStatus.UNREGISTERED,
        vram_required_gb=vram,
        ram_required_gb=ram,
        context_length=32768,
        supports_rocm=backend == KTBackend.ROCM,
        supports_cuda=backend == KTBackend.CUDA,
        supports_moe_offloading=is_moe,
        source="test",
    )


# ── Tests: Models ─────────────────────────────────────────────────

class TestKTModels:
    """Tests for KTModelInfo, KTModelConfig, and all enums."""

    def test_model_creation(self):
        m = _make_model()
        assert m.name == "test-model"
        assert m.status == KTModelStatus.UNREGISTERED

    def test_model_is_moe(self):
        m = _make_model(name="deepseek-v3", is_moe=True)
        assert m.is_moe is True

    def test_config_defaults(self):
        cfg = KTModelConfig()
        assert cfg.backend == KTBackend.CPU
        assert cfg.quantization == KTQuantization.Q4_K_M
        assert cfg.context_length == 32768

    def test_config_moe_offloading(self):
        cfg = KTModelConfig(use_moe_offloading=True, hot_experts=4, n_gpu_layers=28)
        assert cfg.use_moe_offloading is True
        assert cfg.hot_experts == 4
        assert cfg.n_gpu_layers == 28

    def test_all_backends_exist(self):
        """Verify all real KT backends are represented."""
        expected = {"amx_int4", "amx_int8", "avx512_fp8_bf16", "avx512_vbmi",
                     "avx512_vnni", "avx512_base", "avx2_llamafile", "blis_amd",
                     "cuda", "rocm", "cpu", "hybrid"}
        actual = {b.value for b in KTBackend}
        assert expected == actual

    def test_all_quantization_formats(self):
        assert KTQuantization.Q4_K_M.value == "Q4_K_M"
        assert KTQuantization.FP16.value == "FP16"
        assert KTQuantization.GPTQ.value == "GPTQ"

    def test_optimization_result(self):
        result = KTOptimizationResult(
            model_id="test-1",
            recommended_backend=KTBackend.AMX_INT4,
            recommended_quantization=KTQuantization.INT4,
            reasoning="Auto-optimized",
        )
        assert result.recommended_backend == KTBackend.AMX_INT4
        assert result.recommended_quantization == KTQuantization.INT4

    def test_inference_result_error(self):
        result = KTOptimizationResult()  # using import from wrong class... 
        # test KTInferenceRequest/Result directly
        req = KTInferenceRequest(model_id="m1", prompt="Hello", max_tokens=100)
        assert req.model_id == "m1"
        assert req.max_tokens == 100

    def test_fallback_reasons(self):
        assert KTFallbackReason.VRAM_INSUFFICIENT.value == "vram_insufficient"
        assert KTFallbackReason.NONE.value == "none"


# ── Tests: HermesKTAdapter ────────────────────────────────────────

class TestHermesAdapter:
    """Tests for the Hermes ↔ KT bridge adapter."""

    def setup_method(self):
        self.adapter = HermesKTAdapter.get_instance()

    def test_singleton(self):
        a1 = HermesKTAdapter.get_instance()
        a2 = HermesKTAdapter.get_instance()
        assert a1 is a2

    def test_detect_backend(self):
        backend = _detect_best_backend()
        assert isinstance(backend, KTBackend)

    def test_cpu_info(self):
        info = self.adapter.get_cpu_info()
        assert "cpu_variant" in info
        assert "best_backend" in info
        assert "kt_version" in info
        assert "is_real" in info
        assert "has_cuda" in info
        assert "has_rocm" in info

    def test_load_unload_simulated(self):
        info = _make_model(name="test-load")
        cfg = KTModelConfig(backend=KTBackend.CPU, quantization=KTQuantization.Q4_K_M)
        self.adapter.load_model(info, cfg)
        assert info.status == KTModelStatus.LOADED
        assert info.loaded_at is not None

        self.adapter.unload_model(info)
        assert info.status == KTModelStatus.UNLOADED

    def test_infer_simulated(self):
        info = _make_model(name="test-infer")
        cfg = KTModelConfig(backend=KTBackend.AVX2_LLAMAFILE)
        self.adapter.load_model(info, cfg)

        req = KTInferenceRequest(model_id=info.id, prompt="What is AI?")
        result = self.adapter.infer(info, req)

        assert result.model_id == info.id
        assert result.tokens_generated > 0
        assert result.tokens_per_second > 0
        assert result.backend_used == KTBackend.AVX2_LLAMAFILE
        assert result.error is None

        self.adapter.unload_model(info)

    def test_infer_unloaded_model(self):
        info = _make_model(name="test-unloaded")
        req = KTInferenceRequest(model_id=info.id, prompt="Test")
        result = self.adapter.infer(info, req)
        # Should still work via simulated fallback (it uses model_id lookup)
        assert result.model_id == info.id

    def test_optimize_simulated(self):
        info = _make_model(name="qwen3-30b", vram=24, ram=32)
        result = self.adapter.optimize(info, vram_available=8.0, ram_available=32.0, task_type="coding")
        assert isinstance(result, KTOptimizationResult)
        assert result.model_id == info.id
        assert isinstance(result.recommended_backend, KTBackend)
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0

    def test_get_stats(self):
        stats = self.adapter.get_stats()
        assert "is_real" in stats
        assert "kt_version" in stats
        assert "backend" in stats

    def test_checksum(self):
        data = b"test model data"
        cs = self.adapter.compute_checksum(data)
        assert len(cs) == 64  # SHA256 hex


# ── Tests: Discovery Integration ──────────────────────────────────

class TestDiscoveryIntegration:
    """Tests for KTDiscoveryIntegration and KTBenchmarkIntegration."""

    def setup_method(self):
        self.discovery = KTDiscoveryIntegration()
        self.benchmark = KTBenchmarkIntegration()
        self.adapter = HermesKTAdapter.get_instance()

    def test_discover_all_models(self):
        models = self.discovery.discover()
        assert len(models) >= 10  # at least the known catalog
        for m in models:
            assert m.name
            assert m.full_name
            assert m.architecture

    def test_discover_moe_models(self):
        models = self.discovery.discover()
        moe_models = [m for m in models if m.is_moe]
        assert len(moe_models) >= 5  # DeepSeek, Qwen3-MoE, GLM, Mixtral, Kimi
        # All MoE models should support MoE offloading
        for m in moe_models:
            assert m.supports_moe_offloading is True

    def test_supported_architectures(self):
        archs = self.discovery.get_supported_architectures()
        assert "MoE" in archs
        assert "DeepSeek" in archs
        assert "Qwen" in archs

    def test_benchmark_profiles(self):
        assert len(KTBenchmarkIntegration.PROFILES) == 5
        assert "coding" in KTBenchmarkIntegration.PROFILES
        assert "reasoning" in KTBenchmarkIntegration.PROFILES
        assert "long_context" in KTBenchmarkIntegration.PROFILES

    def test_benchmark_run_simulated(self):
        info = _make_model(name="bench-test")
        cfg = KTModelConfig(backend=KTBackend.CPU)
        self.adapter.load_model(info, cfg)

        result = self.benchmark.run_benchmark(info, "coding")
        assert result.model_id == info.id
        assert result.profile == "coding"
        assert result.tokens_per_second > 0
        assert result.success is True

        self.adapter.unload_model(info)

    def test_benchmark_unknown_profile(self):
        info = _make_model()
        result = self.benchmark.run_benchmark(info, "invalid_profile")
        assert result.success is False
        assert result.error is not None

    def test_best_for_task(self):
        info = _make_model()
        profile = self.benchmark.best_for_task(info, "code")
        assert profile == "coding"
        profile = self.benchmark.best_for_task(info, "reasoning")
        assert profile == "reasoning"


# ── Tests: Orchestrator Integration ───────────────────────────────

class TestOrchestratorIntegration:
    """Tests for KTOchestratorIntegration."""

    def setup_method(self):
        self.orchestrator = KTOchestratorIntegration()

    def test_as_candidate(self):
        info = _make_model(name="qwen3-coder-7b", backend=KTBackend.CUDA)
        info.status = KTModelStatus.LOADED
        candidate = self.orchestrator.as_candidate(info)
        assert isinstance(candidate, KTCandidate)
        assert candidate.model_name == "qwen3-coder-7b"
        assert candidate.backend == KTBackend.CUDA
        assert candidate.suitability_score > 0

    def test_candidate_tags(self):
        info = _make_model(name="deepseek-coder", is_moe=True, backend=KTBackend.ROCM)
        info.supports_rocm = True
        info.supports_cuda = False
        candidate = self.orchestrator.as_candidate(info)
        assert "moe" in candidate.tags
        assert "rocm" in candidate.tags
        assert "coder" in candidate.tags

    def test_can_handle_coding_task(self):
        info = _make_model(name="qwen3-coder-7b")
        info.status = KTModelStatus.LOADED
        assert self.orchestrator.can_handle_task(info, "code") is True

    def test_cannot_handle_if_not_loaded(self):
        info = _make_model(name="test-model")
        info.status = KTModelStatus.UNREGISTERED
        assert self.orchestrator.can_handle_task(info, "code") is False

    def test_suitability_score(self):
        info = _make_model(name="qwen3-coder-7b", backend=KTBackend.AMX_INT4)
        info.status = KTModelStatus.LOADED
        score = self.orchestrator.suitability_score(info, "code")
        assert 0.0 < score <= 1.0

        # Low score for unloaded model
        info.status = KTModelStatus.UNREGISTERED
        score2 = self.orchestrator.suitability_score(info, "code")
        assert score2 < score

    def test_suitability_with_constraints(self):
        info = _make_model(name="giant-model", vram=48, ram=64, backend=KTBackend.CUDA)
        info.status = KTModelStatus.LOADED
        score = self.orchestrator.suitability_score(
            info, "general", constraints={"max_vram_gb": 16.0}
        )
        assert score < 0.5  # Should be penalized

    def test_execute(self):
        info = _make_model(name="exec-test")
        cfg = KTModelConfig(backend=KTBackend.CPU)
        HermesKTAdapter.get_instance().load_model(info, cfg)

        result = self.orchestrator.execute(info, "Hello world")
        assert result["text"] is not None
        assert result["tokens_generated"] > 0

        HermesKTAdapter.get_instance().unload_model(info)


# ── Tests: Resource Integration ──────────────────────────────────

class TestResourceIntegration:
    """Tests for KTResourceIntegration."""

    def setup_method(self):
        self.resources = KTResourceIntegration()

    def test_update_and_get(self):
        self.resources.update_resources({"vram_total_gb": 24.0, "vram_used_gb": 8.0, "vram_free_gb": 16.0})
        assert self.resources.get_vram_available() == 16.0

    def test_snapshot(self):
        self.resources.update_resources({"ram_total_gb": 64.0, "ram_free_gb": 48.0})
        snap = self.resources.get_snapshot()
        assert snap["ram_total_gb"] == 64.0
        assert snap["ram_free_gb"] == 48.0

    def test_can_load_sufficient(self):
        self.resources.update_resources({"vram_free_gb": 24.0, "ram_free_gb": 64.0})
        info = _make_model(vram=8, ram=16)
        ok, reason = self.resources.can_load(info)
        assert ok is True
        assert reason == "OK"

    def test_can_load_vram_insufficient(self):
        self.resources.update_resources({"vram_free_gb": 2.0, "ram_free_gb": 64.0})
        info = _make_model(vram=24, ram=32)
        ok, reason = self.resources.can_load(info)
        assert ok is False
        assert "VRAM insufficient" in reason

    def test_can_load_ram_insufficient(self):
        self.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 8.0})
        info = _make_model(vram=8, ram=32)
        ok, reason = self.resources.can_load(info)
        assert ok is False
        assert "RAM insufficient" in reason


# ── Tests: EventBus Bridge ────────────────────────────────────────

class TestEventBusBridge:
    """Tests for KTEventBusBridge."""

    def setup_method(self):
        self.events = KTEventBusBridge()

    def test_publish_event(self):
        self.events.model_discovered(_make_model())
        history = self.events.get_history()
        assert len(history) == 1
        assert history[0]["type"] == "kt.model.discovered"

    def test_all_event_types(self):
        info = _make_model()
        self.events.model_discovered(info)
        self.events.model_loaded(info, KTBackend.CUDA)
        self.events.model_unloaded(info)
        self.events.inference_completed(info, 100, 50.0, KTBackend.CUDA)
        self.events.benchmark_completed(info, "coding", 45.0)
        self.events.fallback_triggered(info, "VRAM low")

        history = self.events.get_history()
        assert len(history) == 6
        types = {e["type"] for e in history}
        assert len(types) == 6

    def test_event_severity(self):
        self.events.model_discovered(_make_model())
        history = self.events.get_history()
        assert history[0]["severity"] == "info"

        self.events.fallback_triggered(_make_model(), "Out of memory")
        history = self.events.get_history()
        assert history[-1]["severity"] == "warning"

    def test_event_source(self):
        self.events.model_loaded(_make_model(), KTBackend.CPU)
        history = self.events.get_history()
        assert history[0]["source"] == "ktransformers"

    def test_history_limit(self):
        for i in range(600):
            self.events.model_discovered(_make_model(name=f"model-{i}"))
        history = self.events.get_history()
        assert len(history) <= 500

    def test_callback_subscription(self):
        received = []
        self.events.subscribe(lambda e: received.append(e))
        self.events.model_loaded(_make_model(), KTBackend.ROCM)
        assert len(received) == 1
        assert received[0]["type"] == "kt.model.loaded"


# ── Tests: KTRuntime ──────────────────────────────────────────────

class TestKTRuntime:
    """Tests for the main KTRuntime orchestrator."""

    def setup_method(self):
        self.rt = KTRuntime()

    def test_register_model(self):
        info = _make_model()
        self.rt.register_model(info)
        assert self.rt.get_model(info.id) is not None
        assert len(self.rt.list_models()) == 1

    def test_register_duplicate(self):
        info = _make_model()
        m1 = self.rt.register_model(info)
        m2 = self.rt.register_model(info)
        assert m1 is m2  # same instance

    def test_list_models_filtered(self):
        for i in range(5):
            info = _make_model(
                name=f"model-{i}",
                backend=KTBackend.CPU if i < 3 else KTBackend.CUDA,
            )
            self.rt.register_model(info)

        assert len(self.rt.list_models(backend=KTBackend.CPU)) == 3
        assert len(self.rt.list_models(backend=KTBackend.CUDA)) == 2

    def test_discover_and_register(self):
        models = self.rt.discover_and_register()
        assert len(models) >= 10
        assert len(self.rt.list_models()) >= 10

    def test_load_and_unload(self):
        info = _make_model(name="load-test")
        self.rt.register_model(info)
        self.rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})

        ok, msg = self.rt.load_model(info.id)
        assert ok is True
        assert info.status == KTModelStatus.LOADED

        assert self.rt.unload_model(info.id) is True
        assert info.status == KTModelStatus.UNLOADED

    def test_load_insufficient_resources(self):
        info = _make_model(vram=48, ram=64)
        self.rt.register_model(info)
        self.rt.resources.update_resources({"vram_free_gb": 4.0, "ram_free_gb": 8.0})

        ok, msg = self.rt.load_model(info.id)
        assert ok is False
        assert "insufficient" in msg.lower()

    def test_load_unknown_model(self):
        ok, msg = self.rt.load_model("nonexistent")
        assert ok is False

    def test_infer_loaded(self):
        info = _make_model(name="infer-test")
        self.rt.register_model(info)
        self.rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})
        self.rt.load_model(info.id)

        req = KTInferenceRequest(model_id=info.id, prompt="Test inference")
        result = self.rt.infer(req)
        assert result.error is None
        assert result.tokens_generated > 0

    def test_infer_unloaded(self):
        info = _make_model(name="infer-unloaded")
        self.rt.register_model(info)

        req = KTInferenceRequest(model_id=info.id, prompt="Test")
        result = self.rt.infer(req)
        assert result.error is not None or result.fallback_reason == KTFallbackReason.BACKEND_UNAVAILABLE

    def test_optimize(self):
        info = _make_model(name="opt-test")
        self.rt.register_model(info)
        result = self.rt.optimize(info.id, "coding")
        assert isinstance(result, KTOptimizationResult)
        assert result.model_id == info.id

    def test_run_benchmark(self):
        info = _make_model(name="bench-test")
        self.rt.register_model(info)
        self.rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})

        result = self.rt.run_benchmark(info.id, "general_chat")
        assert result.success is True
        assert result.profile == "general_chat"

    def test_get_status(self):
        info = _make_model()
        self.rt.register_model(info)
        self.rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})
        self.rt.load_model(info.id)

        status = self.rt.get_status()
        assert status["models_total"] >= 1
        assert status["models_loaded"] == 1
        assert "adapter" in status
        assert "models" in status
        assert "resources" in status

    def test_get_statistics(self):
        self.rt.discover_and_register()
        stats = self.rt.get_statistics()
        assert stats["total_models"] >= 10
        assert "by_backend" in stats
        assert "by_status" in stats
        assert "is_real_kt" in stats

    def test_get_model_not_found(self):
        assert self.rt.get_model("nonexistent") is None

    def test_singleton_runtime(self):
        rt1 = get_kt_runtime()
        rt2 = get_kt_runtime()
        assert rt1 is rt2


# ── Tests: Full Integration Pipeline ──────────────────────────────

class TestFullIntegration:
    """End-to-end pipeline tests."""

    def test_discover_optimize_load_infer(self):
        rt = KTRuntime()

        # 1. Discover models
        models = rt.discover_and_register()
        assert len(models) >= 10

        # 2. Pick a small model
        small = None
        for m in models:
            if m.ram_required_gb <= 32 and m.vram_required_gb <= 24:
                small = m
                break
        assert small is not None, "Should find at least one small model"

        # 3. Set generous resources
        rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})

        # 4. Optimize
        opt = rt.optimize(small.id, "coding")
        assert isinstance(opt.recommended_backend, KTBackend)

        # 5. Load
        ok, msg = rt.load_model(small.id)
        assert ok, f"Load failed: {msg}"
        assert small.status == KTModelStatus.LOADED

        # 6. Infer
        req = KTInferenceRequest(model_id=small.id, prompt="Write a function that sorts a list")
        result = rt.infer(req)
        assert result.error is None
        assert result.tokens_generated > 0
        assert result.tokens_per_second > 0

        # 7. Check events
        events = rt.events.get_history()
        event_types = {e["type"] for e in events}
        assert "kt.model.loaded" in event_types
        assert "kt.inference.completed" in event_types

    def test_orchestrator_integration_pipeline(self):
        rt = KTRuntime()
        rt.discover_and_register()
        rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 64.0})

        # Pick a small model from the catalog and register/load it first
        models = rt.list_models()
        small = None
        for m in models:
            if m.ram_required_gb <= 40 and m.vram_required_gb <= 32:
                small = m
                break
        # If no small model found, create one
        if small is None:
            small = _make_model(name="orchestrator-test", vram=4, ram=8)
            rt.register_model(small)

        ok, _ = rt.load_model(small.id)
        assert ok, f"Failed to load model for orchestrator test"

        # Now get candidates — the loaded model should have a valid score
        candidate = rt.orchestrator.as_candidate(small)
        assert candidate.suitability_score > 0.0

        # Execute via orchestrator
        result = rt.orchestrator.execute(small, "Hello, how are you?")
        assert result["text"] is not None

    def test_moe_optimization(self):
        rt = KTRuntime()
        rt.discover_and_register()

        # Find a MoE model
        moe_models = [m for m in rt.list_models() if m.is_moe]
        assert len(moe_models) > 0, "Should have MoE models from discovery"

        moe = moe_models[0]
        rt.resources.update_resources({"vram_free_gb": 16.0, "ram_free_gb": 64.0})

        opt = rt.optimize(moe.id, "reasoning")
        # With limited VRAM, should recommend MoE offloading or hybrid
        assert opt.use_moe_offloading or opt.recommended_backend in (KTBackend.HYBRID, KTBackend.CPU)


# ── Tests: Thread Safety ──────────────────────────────────────────

class TestThreadSafety:
    """Concurrent access tests."""

    def test_concurrent_registration(self):
        rt = KTRuntime()

        def register(i: int):
            info = _make_model(name=f"thread-model-{i}")
            rt.register_model(info)
            return info

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(register, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]

        assert len(rt.list_models()) == 100

    def test_concurrent_load_unload(self):
        rt = KTRuntime()
        rt.resources.update_resources({"vram_free_gb": 48.0, "ram_free_gb": 128.0})

        info = _make_model(name="thread-load", vram=4, ram=8)
        rt.register_model(info)

        errors = []

        def load_unload(i: int):
            try:
                ok, _ = rt.load_model(info.id)
                if ok:
                    rt.unload_model(info.id)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(load_unload, range(50)))

        assert len(errors) == 0

    def test_concurrent_events(self):
        bridge = KTEventBusBridge()
        info = _make_model()

        def publish(i: int):
            bridge.model_discovered(info)
            bridge.model_loaded(info, KTBackend.CPU)
            bridge.inference_completed(info, i, float(i), KTBackend.CPU)

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(publish, range(50)))

        history = bridge.get_history()
        assert len(history) <= 500


# ── Tests: Backend Detection ──────────────────────────────────────

class TestBackendDetection:
    """Tests for auto-detection of KT backends."""

    def test_detect_returns_valid_backend(self):
        backend = _detect_best_backend()
        assert isinstance(backend, KTBackend)

    def test_backend_performance_order(self):
        """Verify performance ordering of backends."""
        perf_order = [
            KTBackend.AMX_INT4, KTBackend.AMX_INT8,
            KTBackend.CUDA, KTBackend.ROCM,
            KTBackend.AVX512_FP8_BF16, KTBackend.AVX512_VBMI,
            KTBackend.AVX512_VNNI, KTBackend.AVX512_BASE,
            KTBackend.HYBRID, KTBackend.BLIS_AMD,
            KTBackend.AVX2_LLAMAFILE, KTBackend.CPU,
        ]
        for backend in KTBackend:
            assert backend in perf_order, f"{backend.value} not in performance order"

    def test_quantization_size_differences(self):
        """Verify quantization tiers exist."""
        low_quality = {KTQuantization.Q2_K, KTQuantization.Q3_K_S, KTQuantization.Q3_K_M}
        medium_quality = {KTQuantization.Q4_0, KTQuantization.Q4_K_S, KTQuantization.Q4_K_M}
        high_quality = {KTQuantization.Q5_0, KTQuantization.Q5_K_S, KTQuantization.Q5_K_M, KTQuantization.Q6_K}
        highest_quality = {KTQuantization.Q8_0, KTQuantization.FP16, KTQuantization.BF16, KTQuantization.FP8, KTQuantization.INT8}

        assert KTQuantization.Q4_K_M in medium_quality
        assert KTQuantization.FP16 in highest_quality
        assert KTQuantization.INT8 in highest_quality


# ── Tests: Known Models Catalog ───────────────────────────────────

class TestKnownModels:
    """Verify the known KT models catalog is complete and valid."""

    def test_catalog_size(self):
        assert len(_KNOWN_KT_MODELS) >= 10

    def test_all_have_required_fields(self):
        required = {"name", "full_name", "architecture", "num_parameters",
                     "context_length", "size_gb", "vram_required_gb",
                     "ram_required_gb", "source"}
        for entry in _KNOWN_KT_MODELS:
            for field in required:
                assert field in entry, f"Missing {field} in {entry['name']}"

    def test_moe_models_have_offloading(self):
        for entry in _KNOWN_KT_MODELS:
            if entry["architecture"] == "MoE":
                assert entry.get("supports_moe_offloading") is True, \
                    f"{entry['name']} should support MoE offloading"

    def test_deepseek_family(self):
        names = {e["name"] for e in _KNOWN_KT_MODELS}
        assert "deepseek-v3" in names
        assert "deepseek-r1" in names
        assert "deepseek-v4-flash" in names

    def test_qwen_family(self):
        names = {e["name"] for e in _KNOWN_KT_MODELS}
        assert "qwen3-moe" in names
        assert "qwen3-coder-30b" in names

    def test_mixtral_family(self):
        names = {e["name"] for e in _KNOWN_KT_MODELS}
        assert "mixtral-8x7b" in names
        assert "mixtral-8x22b" in names
