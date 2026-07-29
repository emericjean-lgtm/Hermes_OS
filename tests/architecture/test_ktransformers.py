"""Tests for HOS-052 — KTransformers Runtime Integration."""

from __future__ import annotations

import threading
import time

import pytest

from backend.runtime.ktransformers import (
    KTBackend,
    KTCache,
    KTFallbackReason,
    KTInferenceRequest,
    KTLoadConfig,
    KTLoader,
    KTModelInfo,
    KTModelManager,
    KTModelStatus,
    KTOptimizer,
    KTQuantization,
    KTRuntime,
    KTScheduler,
)


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def model_manager():
    return KTModelManager()


@pytest.fixture
def cache():
    return KTCache(max_entries=8, default_ttl_s=600.0)


@pytest.fixture
def loader(model_manager, cache):
    return KTLoader(model_manager, cache)


@pytest.fixture
def scheduler():
    return KTScheduler(max_concurrent=4)


@pytest.fixture
def optimizer():
    return KTOptimizer()


@pytest.fixture
def runtime():
    return KTRuntime()


@pytest.fixture
def sample_model():
    return KTModelInfo(
        name="test-model-7b",
        path="/models/test-7b-q4.gguf",
        quantization=KTQuantization.Q4_K_M,
        size_gb=4.0,
        size_params="7B",
        architecture="llama",
        backend=KTBackend.ROCM,
        tags=["chat", "coding"],
    )


# ── Model Manager ─────────────────────────────────────

class TestKTModelManager:
    def test_register_model(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert model_manager.total_models() == 1

    def test_get_model(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        found = model_manager.get(sample_model.id)
        assert found is not None
        assert found.name == "test-model-7b"

    def test_get_nonexistent(self, model_manager: KTModelManager):
        assert model_manager.get("nonexistent") is None

    def test_list_all(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert len(model_manager.list_all()) == 1

    def test_list_by_status(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        available = model_manager.list_by_status(KTModelStatus.REGISTERED)
        assert len(available) == 1
        loaded = model_manager.list_by_status(KTModelStatus.LOADED)
        assert len(loaded) == 0

    def test_list_by_backend(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert len(model_manager.list_by_backend(KTBackend.ROCM)) == 1
        assert len(model_manager.list_by_backend(KTBackend.CPU)) == 0

    def test_search(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert len(model_manager.search("test")) == 1
        assert len(model_manager.search("nonexistent")) == 0
        assert len(model_manager.search("chat")) == 1  # tag

    def test_update_status(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert model_manager.update_status(sample_model.id, KTModelStatus.DOWNLOADING)
        assert model_manager.get(sample_model.id).status == KTModelStatus.DOWNLOADING

    def test_remove(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert model_manager.remove(sample_model.id)
        assert model_manager.total_models() == 0

    def test_simulate_download(self, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert model_manager.simulate_download(sample_model.id)
        assert model_manager.get(sample_model.id).status == KTModelStatus.AVAILABLE

    def test_checksum(self, model_manager: KTModelManager):
        cs = KTModelManager.compute_checksum("/tmp/test.gguf", 1000)
        assert len(cs) == 64
        cs2 = KTModelManager.compute_checksum("/tmp/test.gguf", 1000)
        assert cs == cs2  # Deterministic
        cs3 = KTModelManager.compute_checksum("/tmp/other.gguf", 1000)
        assert cs != cs3  # Different path

    def test_count_by_status(self, model_manager: KTModelManager):
        m1 = KTModelInfo(name="a", status=KTModelStatus.AVAILABLE, size_gb=1)
        m2 = KTModelInfo(name="b", status=KTModelStatus.LOADED, size_gb=2)
        model_manager.register(m1)
        model_manager.register(m2)
        counts = model_manager.count_by_status()
        assert counts.get("available") == 1
        assert counts.get("loaded") == 1


# ── Cache ─────────────────────────────────────────────

class TestKTCache:
    def test_add_and_get(self, cache: KTCache):
        assert cache.add("model-1", size_gb=2.0)
        entry = cache.get("model-1")
        assert entry is not None
        assert entry.model_id == "model-1"
        assert entry.size_gb == 2.0

    def test_add_duplicate(self, cache: KTCache):
        assert cache.add("model-1")
        assert cache.add("model-1")  # Should update access time

    def test_miss(self, cache: KTCache):
        assert cache.get("missing") is None

    def test_remove(self, cache: KTCache):
        cache.add("model-1")
        assert cache.remove("model-1")
        assert cache.get("model-1") is None

    def test_contains(self, cache: KTCache):
        cache.add("model-1")
        assert cache.contains("model-1")
        assert not cache.contains("model-2")

    def test_eviction_on_full(self, cache: KTCache):
        small = KTCache(max_entries=3, default_ttl_s=600.0)
        small.add("a")
        small.add("b")
        small.add("c")
        small.add("d")  # Should evict least recently accessed
        assert small.size() == 3

    def test_clear(self, cache: KTCache):
        cache.add("a")
        cache.add("b")
        assert cache.clear() == 2
        assert cache.size() == 0

    def test_stats(self, cache: KTCache):
        cache.add("model-1")
        cache.get("model-1")  # hit
        cache.get("model-2")  # miss
        stats = cache.stats()
        assert stats.hit_count == 1
        assert stats.miss_count == 1
        assert stats.total_entries == 1

    def test_priority_eviction(self):
        cache = KTCache(max_entries=2, default_ttl_s=600.0)
        cache.add("a", priority=0)
        cache.add("b", priority=2)
        cache.add("c", priority=0)  # Should evict "a" (lower priority)
        assert cache.contains("b")
        assert cache.contains("c")


# ── Loader ────────────────────────────────────────────

class TestKTLoader:
    def test_load_model(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        config = KTLoadConfig(model_id=sample_model.id, backend=KTBackend.ROCM)
        assert loader.load(config)
        assert loader.is_loaded(sample_model.id)
        assert model_manager.get(sample_model.id).status == KTModelStatus.LOADED

    def test_load_nonexistent(self, loader: KTLoader):
        config = KTLoadConfig(model_id="nonexistent")
        assert not loader.load(config)

    def test_double_load(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        config = KTLoadConfig(model_id=sample_model.id)
        assert loader.load(config)
        assert loader.load(config)  # Idempotent
        assert loader.loaded_count() == 1

    def test_unload(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        config = KTLoadConfig(model_id=sample_model.id)
        loader.load(config)
        assert loader.unload(sample_model.id)
        assert not loader.is_loaded(sample_model.id)

    def test_ensure_loaded(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        assert loader.ensure_loaded(sample_model.id)
        assert loader.is_loaded(sample_model.id)

    def test_auto_unload_idle(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        model_manager.register(sample_model)
        config = KTLoadConfig(model_id=sample_model.id)
        loader.load(config)
        unloaded = loader.auto_unload_idle(max_idle_seconds=-1)  # Everything is idle
        assert len(unloaded) == 1

    def test_unload_all(self, loader: KTLoader, model_manager: KTModelManager, sample_model: KTModelInfo):
        m2 = KTModelInfo(name="model-2", size_gb=1)
        model_manager.register(sample_model)
        model_manager.register(m2)
        loader.load(KTLoadConfig(model_id=sample_model.id))
        loader.load(KTLoadConfig(model_id=m2.id))
        assert loader.unload_all() == 2
        assert loader.loaded_count() == 0


# ── Scheduler ─────────────────────────────────────────

class TestKTScheduler:
    def test_enqueue_dequeue(self, scheduler: KTScheduler):
        req = KTInferenceRequest(model_id="m1", prompt="Hello")
        scheduler.enqueue(req, priority=1)
        dequeued = scheduler.dequeue_next()
        assert dequeued is not None
        assert dequeued.prompt == "Hello"

    def test_priority_ordering(self, scheduler: KTScheduler):
        low = KTInferenceRequest(model_id="m1", prompt="low")
        high = KTInferenceRequest(model_id="m2", prompt="high")
        scheduler.enqueue(low, priority=0)
        scheduler.enqueue(high, priority=3)
        # High priority dequeued first
        first = scheduler.dequeue_next()
        assert first is not None
        assert first.prompt == "high"

    def test_cancel(self, scheduler: KTScheduler):
        req = KTInferenceRequest(model_id="m1", prompt="test")
        scheduler.enqueue(req, priority=1)
        assert scheduler.cancel(req.id)

    def test_process_batch(self, scheduler: KTScheduler):
        for i in range(5):
            scheduler.enqueue(KTInferenceRequest(model_id="m1", prompt=f"test-{i}"))
        results = scheduler.process_batch(max_batch=4)
        assert len(results) == 4
        for r in results:
            assert r.tokens_generated > 0

    def test_stats(self, scheduler: KTScheduler):
        req = KTInferenceRequest(model_id="m1", prompt="test")
        scheduler.enqueue(req)
        scheduler.process_batch(max_batch=1)
        stats = scheduler.stats()
        assert stats.completed_requests == 1

    def test_cancel_all(self, scheduler: KTScheduler):
        for i in range(3):
            scheduler.enqueue(KTInferenceRequest(model_id="m1", prompt=f"test-{i}"))
        assert scheduler.cancel_all() == 3
        assert scheduler.queue_length() == 0


# ── Optimizer ─────────────────────────────────────────

class TestKTOptimizer:
    def test_optimize_chat_7b(self, optimizer: KTOptimizer):
        optimizer.set_hardware(vram_free=12.0, ram_free=24.0)
        result = optimizer.optimize("7B", task_type="chat")
        assert result.recommended_quantization == KTQuantization.Q4_K_M
        assert result.can_fit_vram
        assert not result.fallback_needed

    def test_optimize_coding_prefers_quality(self, optimizer: KTOptimizer):
        optimizer.set_hardware(vram_free=16.0, ram_free=24.0)
        result = optimizer.optimize("7B", task_type="coding")
        assert result.recommended_quantization == KTQuantization.Q5_K_M  # coding → Q5

    def test_optimize_low_vram_fallback(self, optimizer: KTOptimizer):
        optimizer.set_hardware(vram_free=2.0, ram_free=24.0)
        result = optimizer.optimize("13B", task_type="chat")
        assert result.fallback_needed
        assert result.fallback_reason is not None

    def test_optimize_very_low_resources(self, optimizer: KTOptimizer):
        optimizer.set_hardware(vram_free=1.0, ram_free=2.0)
        result = optimizer.optimize("70B", task_type="chat")
        assert result.fallback_needed

    def test_capabilities(self, optimizer: KTOptimizer):
        caps = optimizer.get_capabilities()
        assert "vram_total_gb" in caps
        assert "available_backends" in caps


# ── Runtime ───────────────────────────────────────────

class TestKTRuntime:
    def test_register_and_list(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        assert len(runtime.list_models()) == 1

    def test_load_unload(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        assert runtime.load_model(sample_model.id)
        assert runtime.is_model_loaded(sample_model.id)
        assert runtime.unload_model(sample_model.id)
        assert not runtime.is_model_loaded(sample_model.id)

    def test_infer(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        req = KTInferenceRequest(model_id=sample_model.id, prompt="Hello", max_tokens=50)
        result = runtime.infer(req)
        assert result.tokens_generated > 0
        assert result.model_id == sample_model.id

    def test_infer_async(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        req = KTInferenceRequest(model_id=sample_model.id, prompt="Async test")
        req_id = runtime.infer_async(req)
        assert req_id == req.id
        results = runtime.process_pending(max_batch=10)
        assert len(results) == 1

    def test_optimize_for_task(self, runtime: KTRuntime):
        result = runtime.optimize_for_task("7B", "coding")
        assert result.score > 0

    def test_status(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        s = runtime.status()
        assert s["models_total"] == 1
        assert "cache" in s
        assert "scheduler" in s

    def test_statistics(self, runtime: KTRuntime, sample_model: KTModelInfo):
        runtime.register_model(sample_model)
        runtime.load_model(sample_model.id)
        req = KTInferenceRequest(model_id=sample_model.id, prompt="Count this")
        runtime.infer(req)
        stats = runtime.statistics()
        assert stats["scheduler"]["completed"] == 1

    def test_event_callback(self, sample_model: KTModelInfo):
        events = []

        def callback(evt_type, payload):
            events.append((evt_type, payload))

        rt = KTRuntime(event_callback=callback)
        rt.register_model(sample_model)
        rt.load_model(sample_model.id)
        rt.unload_model(sample_model.id)
        assert any(e[0] == "ktransformers.loaded" for e in events)
        assert any(e[0] == "ktransformers.unloaded" for e in events)


# ── Thread Safety ─────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_model_registration(self, model_manager: KTModelManager):
        errors = []

        def register_one(i):
            try:
                m = KTModelInfo(name=f"model-{i}", size_gb=float(i))
                model_manager.register(m)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=register_one, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert model_manager.total_models() == 20

    def test_concurrent_load_unload(self, model_manager: KTModelManager, cache: KTCache):
        loader = KTLoader(model_manager, cache)
        for i in range(10):
            m = KTModelInfo(name=f"m-{i}", size_gb=1.0)
            model_manager.register(m)

        def load_and_unload(i):
            mid = next(m.id for m in model_manager.list_all() if m.name == f"m-{i}")
            loader.load(KTLoadConfig(model_id=mid))
            loader.unload(mid)

        threads = [threading.Thread(target=load_and_unload, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert loader.loaded_count() == 0

    def test_concurrent_scheduler(self):
        scheduler = KTScheduler(max_concurrent=8)

        def send_requests():
            for i in range(10):
                scheduler.enqueue(KTInferenceRequest(model_id="m1", prompt=f"r{i}"))

        def process():
            for _ in range(5):
                scheduler.process_batch(max_batch=2)

        threads = [
            threading.Thread(target=send_requests),
            threading.Thread(target=send_requests),
            threading.Thread(target=process),
            threading.Thread(target=process),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = scheduler.stats()
        assert stats.completed_requests + scheduler.queue_length() == 20


# ── Events ────────────────────────────────────────────

class TestEvents:
    def test_load_unload_events(self, sample_model: KTModelInfo):
        events = []

        def cb(evt, payload):
            events.append(evt)

        rt = KTRuntime(event_callback=cb)
        rt.register_model(sample_model)
        rt.load_model(sample_model.id)
        rt.unload_model(sample_model.id)
        assert "ktransformers.loaded" in events
        assert "ktransformers.unloaded" in events

    def test_optimized_event(self):
        events = []

        def cb(evt, payload):
            events.append(evt)

        rt = KTRuntime(event_callback=cb)
        rt.optimize_for_task("7B", "chat")
        assert "ktransformers.optimized" in events

    def test_fallback_event(self):
        events = []
        rt = KTRuntime(event_callback=lambda e, p: events.append(e))
        rt.optimizer.set_hardware(vram_free=1.0, ram_free=24.0)
        rt.optimize_for_task("13B", "chat")
        assert "ktransformers.fallback" in events
