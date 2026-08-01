"""Model Intelligence Tests for Hermes OS (HOS-065).

Tests model profiling, performance analysis, prediction, adaptive routing,
benchmark scheduling, runtime optimization, and thread safety.
"""

from __future__ import annotations

import threading

import pytest

from backend.model_intelligence.adaptive_router import AdaptiveRouter
from backend.model_intelligence.benchmark_scheduler import BenchmarkScheduler
from backend.model_intelligence.model_intelligence_models import (
    BenchmarkResult,
    ModelArchitecture,
    ModelDecision,
    ModelPerformanceRecord,
    ModelProfile,
    PREDEFINED_MODELS,
    Quantization,
    RuntimeBackend,
    TaskContext,
    TaskType,
)
from backend.model_intelligence.model_predictor import ModelPredictor
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.model_runtime_optimizer import ModelRuntimeOptimizer
from backend.model_intelligence.performance_analyzer import PerformanceAnalyzer
from backend.model_intelligence.routes import (
    handle_get_intelligence,
    handle_get_ranking,
    handle_recommend,
    handle_get_history,
    handle_run_benchmark,
    handle_get_performance,
    handle_get_knowledge,
    handle_get_evolution,
)


# ═══════════════════════════════════════════════════════════════
# Model Profile & Models Tests
# ═══════════════════════════════════════════════════════════════

class TestModelIntelligenceModels:
    def test_model_profile_creation(self):
        profile = ModelProfile(model_id="test", name="Test Model")
        assert profile.model_id == "test"
        assert profile.name == "Test Model"

    def test_model_architecture_enum(self):
        assert ModelArchitecture.LLAMA.value == "llama"
        assert ModelArchitecture.QWEN.value == "qwen"

    def test_task_type_enum(self):
        assert TaskType.CODE_GENERATION.value == "code_generation"
        assert TaskType.DEBUG.value == "debug"

    def test_runtime_backend_enum(self):
        assert RuntimeBackend.OLLAMA.value == "ollama"
        assert RuntimeBackend.KTRANSFORMERS.value == "ktransformers"

    def test_quantization_enum(self):
        assert Quantization.Q4_K_M.value == "q4_k_m"
        assert Quantization.F16.value == "f16"

    def test_task_context_defaults(self):
        ctx = TaskContext()
        assert ctx.task_type == TaskType.GENERAL
        assert ctx.max_vram_mb == 8192

    def test_model_decision_creation(self):
        decision = ModelDecision(
            model_id="test", model_name="Test",
            runtime=RuntimeBackend.OLLAMA,
            quantization=Quantization.Q4_K_M,
            confidence=0.9, reason="Best match",
        )
        assert decision.confidence == 0.9
        assert decision.runtime == RuntimeBackend.OLLAMA

    def test_predefined_models_count(self):
        assert len(PREDEFINED_MODELS) >= 5
        assert "qwen3-coder:30b" in PREDEFINED_MODELS

    def test_predefined_models_come_from_the_real_role_catalogue(self):
        """PREDEFINED_MODELS used to be six fixed entries — llama3.2-3b,
        mistral-7b, codellama-7b, phi3-14b, deepseek-coder-16b,
        qwen3-coder-30b — none of which any deployment of this project has
        ever had installed: the Models Center showed a benchmark
        leaderboard for models nobody could run. Every entry now must be a
        real config/models.yaml role, keyed by that role's actual Ollama tag."""
        from backend.core.config import load_models_config

        real_tags = {r["model"] for r in load_models_config()["roles"].values()}
        assert PREDEFINED_MODELS, "the catalogue must not be empty"
        assert set(PREDEFINED_MODELS) <= real_tags
        fake_ids = {"llama3.2-3b", "mistral-7b", "codellama-7b",
                    "phi3-14b", "deepseek-coder-16b", "qwen3-coder-30b"}
        assert not (set(PREDEFINED_MODELS) & fake_ids)

    def test_performance_record_auto_timestamp(self):
        rec = ModelPerformanceRecord(
            model_id="test", task_type=TaskType.CODE_GENERATION,
            duration_ms=100, tokens_used=500, success=True,
        )
        assert rec.timestamp != ""

    def test_benchmark_result_creation(self):
        bm = BenchmarkResult(
            benchmark_id="bm1", model_id="test",
            task_type=TaskType.ANALYSIS,
            latency_ms=150.0, tokens_per_second=45.0,
            vram_usage_mb=4000, ram_usage_mb=8000,
            quality_score=0.85, temperature=0.2,
        )
        assert bm.quality_score == 0.85
        assert bm.tokens_per_second == 45.0

    def test_profile_success_rate(self):
        profile = ModelProfile(model_id="test", name="Test", total_runs=10, successful_runs=8)
        assert profile.success_rate == 0.8

    def test_profile_overall_score(self):
        profile = ModelProfile(model_id="test", name="Test", benchmark_score=0.5)
        score = profile.overall_score
        assert 0 <= score <= 1.0

    def test_profile_task_scores(self):
        profile = ModelProfile(model_id="test", name="Test",
                               task_scores={"code_generation": 0.9, "debug": 0.8})
        assert profile.task_scores["code_generation"] == 0.9


# ═══════════════════════════════════════════════════════════════
# Model Profiler Tests
# ═══════════════════════════════════════════════════════════════

class TestModelProfiler:
    def test_profiler_creates_predefined(self):
        profiler = ModelProfiler()
        profiles = profiler.list_profiles()
        assert len(profiles) >= 5

    def test_get_profile(self):
        profiler = ModelProfiler()
        profile = profiler.get_profile("qwen3-coder:30b")
        assert profile is not None
        # `name` is the real Ollama tag itself (lowercase) now that the
        # profiler is seeded from config/models.yaml, not a hand-written
        # display string like the old fictional "Qwen3-Coder 30B" was.
        assert "qwen3" in profile.name.lower()

    def test_get_profile_not_found(self):
        profiler = ModelProfiler()
        profile = profiler.get_profile("nonexistent")
        assert profile is None

    def test_register_new_model(self):
        profiler = ModelProfiler()
        new = ModelProfile(model_id="new_model", name="New Model")
        profiler.register_model(new)
        assert profiler.get_profile("new_model") is not None

    def test_get_top_models(self):
        profiler = ModelProfiler()
        top = profiler.get_top_models(limit=3)
        assert len(top) <= 3
        assert top[0].overall_score >= top[-1].overall_score

    def test_get_top_models_by_task(self):
        profiler = ModelProfiler()
        top = profiler.get_top_models(TaskType.CODE_GENERATION, 2)
        assert len(top) <= 2

    def test_get_models_for_task(self):
        profiler = ModelProfiler()
        suitable = profiler.get_models_for_task(TaskType.CODE_GENERATION, max_vram_mb=20000)
        assert len(suitable) > 0

    def test_get_models_for_task_vram_limit(self):
        profiler = ModelProfiler()
        suitable = profiler.get_models_for_task(TaskType.CODE_GENERATION, max_vram_mb=5000)
        for s in suitable:
            assert s.vram_required_mb <= 5000

    def test_update_performance(self):
        profiler = ModelProfiler()
        profiler.update_performance(ModelPerformanceRecord(
            model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
            duration_ms=1000, tokens_used=200, success=True,
        ))
        profile = profiler.get_profile("qwen3-coder:30b")
        assert profile is not None
        assert profile.total_runs >= 1

    def test_update_performance_derives_real_tokens_per_second(self):
        """tokens_per_second starts honest (0.0, never measured) and should
        reflect a real completion, not the random.uniform() BenchmarkScheduler
        fabricates and never persists (see its module docstring)."""
        profiler = ModelProfiler()
        assert profiler.get_profile("qwen3-coder:30b").tokens_per_second == 0.0

        profiler.update_performance(ModelPerformanceRecord(
            model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
            duration_ms=2000, tokens_used=100, success=True,
        ))
        assert profiler.get_profile("qwen3-coder:30b").tokens_per_second == pytest.approx(50.0)

    def test_update_performance_smooths_repeated_measurements(self):
        profiler = ModelProfiler()
        profiler.update_performance(ModelPerformanceRecord(
            model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
            duration_ms=1000, tokens_used=100, success=True,  # 100 tok/s
        ))
        profiler.update_performance(ModelPerformanceRecord(
            model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
            duration_ms=1000, tokens_used=200, success=True,  # 200 tok/s
        ))
        # A blend (0.7*100 + 0.3*200), not just the latest measurement —
        # one slow/fast outlier shouldn't whiplash the estimate.
        assert profiler.get_profile("qwen3-coder:30b").tokens_per_second == pytest.approx(130.0)

    def test_update_performance_ignores_failed_runs_for_tps(self):
        profiler = ModelProfiler()
        profiler.update_performance(ModelPerformanceRecord(
            model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
            duration_ms=1000, tokens_used=0, success=False,
        ))
        assert profiler.get_profile("qwen3-coder:30b").tokens_per_second == 0.0

    def test_get_performance_history(self):
        profiler = ModelProfiler()
        profiler.update_performance(ModelPerformanceRecord(
            model_id="test", task_type=TaskType.DEBUG,
            duration_ms=500, tokens_used=100, success=True,
        ))
        history = profiler.get_performance_history("test")
        assert len(history) >= 1

    def test_get_stats(self):
        profiler = ModelProfiler()
        stats = profiler.get_stats()
        assert "total_models" in stats
        assert stats["total_models"] >= 5

    def test_profiler_list_profiles_sorted(self):
        profiler = ModelProfiler()
        profiles = profiler.list_profiles()
        for i in range(len(profiles) - 1):
            assert profiles[i].overall_score >= profiles[i + 1].overall_score


# ═══════════════════════════════════════════════════════════════
# Performance Analyzer Tests
# ═══════════════════════════════════════════════════════════════

class TestPerformanceAnalyzer:
    def test_compute_model_score(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test",
                               tokens_per_second=50.0, vram_required_mb=4000,
                               task_scores={"code_generation": 0.9})
        score = analyzer.compute_model_score(profile, [])
        assert 0 <= score <= 1.0

    def test_add_benchmark(self):
        analyzer = PerformanceAnalyzer()
        bm = BenchmarkResult(benchmark_id="bm1", model_id="test",
                             task_type=TaskType.CODE_GENERATION,
                             latency_ms=100.0, tokens_per_second=50.0,
                             vram_usage_mb=4000, ram_usage_mb=8000,
                             quality_score=0.9, temperature=0.2)
        analyzer.add_benchmark(bm)
        summary = analyzer.get_benchmark_summary("test")
        assert summary["count"] == 1

    def test_benchmark_summary_all(self):
        analyzer = PerformanceAnalyzer()
        summary = analyzer.get_benchmark_summary()
        assert summary is not None

    def test_compute_quality_score(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test",
                               task_scores={"code_generation": 0.85, "debug": 0.75})
        score = analyzer.compute_quality_score(profile, [])
        assert score >= 0.7

    def test_compute_speed_score_fast(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test", tokens_per_second=100.0)
        score = analyzer._compute_speed_score(profile)
        assert score == 1.0

    def test_compute_speed_score_slow(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test", tokens_per_second=5.0)
        score = analyzer._compute_speed_score(profile)
        assert score < 0.5

    def test_compute_efficiency_score(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test", vram_required_mb=4000)
        score = analyzer._compute_efficiency_score(profile)
        assert score > 0.9

    def test_compute_efficiency_score_high_vram(self):
        analyzer = PerformanceAnalyzer()
        profile = ModelProfile(model_id="test", name="Test", vram_required_mb=72000)
        score = analyzer._compute_efficiency_score(profile)
        assert score < 0.2


# ═══════════════════════════════════════════════════════════════
# Model Predictor Tests
# ═══════════════════════════════════════════════════════════════

class TestModelPredictor:
    def test_predict_latency(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", latency_ms=200.0)
        task = TaskContext(complexity=0.5)
        latency = predictor.predict_latency(profile, task)
        assert latency > 200.0

    def test_predict_tps(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", tokens_per_second=50.0)
        task = TaskContext(complexity=0.3)
        tps = predictor.predict_tokens_per_second(profile, task)
        assert tps > 0

    def test_predict_tps_estimated(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", parameters_b=7.0)
        task = TaskContext()
        tps = predictor.predict_tokens_per_second(profile, task)
        assert tps > 0

    def test_predict_success_probability(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", historical_success_rate=0.9)
        prob = predictor.predict_success_probability(profile, [], TaskContext())
        assert prob > 0.5

    def test_predict_vram_usage(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", vram_required_mb=4000)
        task = TaskContext(complexity=0.5)
        vram = predictor.predict_vram_usage(profile, task)
        assert vram >= 4000

    def test_rank_models(self):
        predictor = ModelPredictor()
        profiles = [
            ModelProfile(model_id="a", name="A", parameters_b=7, tokens_per_second=50,
                        vram_required_mb=4000, task_scores={"code_generation": 0.9}),
            ModelProfile(model_id="b", name="B", parameters_b=3, tokens_per_second=80,
                        vram_required_mb=2000, task_scores={"code_generation": 0.7}),
        ]
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        ranked = predictor.rank_models(profiles, [], task)
        assert len(ranked) >= 1
        assert ranked[0]["score"] >= ranked[-1]["score"]

    def test_log_prediction(self):
        predictor = ModelPredictor()
        predictor.log_prediction("test", "code_generation", 0.9, True)
        history = predictor.get_prediction_history()
        assert len(history) >= 1

    def test_rank_models_vram_filter(self):
        predictor = ModelPredictor()
        profiles = [
            ModelProfile(model_id="big", name="Big", parameters_b=70,
                        vram_required_mb=40000, task_scores={"code_generation": 0.9}),
        ]
        task = TaskContext(max_vram_mb=8000)
        ranked = predictor.rank_models(profiles, [], task)
        assert len(ranked) == 0  # Exceeds VRAM limit


# ═══════════════════════════════════════════════════════════════
# Adaptive Router Tests
# ═══════════════════════════════════════════════════════════════

class TestAdaptiveRouter:
    def test_recommend_code_generation(self):
        router = AdaptiveRouter()
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_vram_mb=20000)
        decision = router.recommend(task)
        assert decision.confidence > 0
        assert decision.model_id != ""

    def test_recommend_with_vram_constraint(self):
        router = AdaptiveRouter()
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_vram_mb=3000)
        decision = router.recommend(task)
        assert decision.estimated_vram_mb <= 3000 or "fallback" in decision.reason.lower()

    def test_recommend_for_text_optimization(self):
        router = AdaptiveRouter()
        decision = router.recommend_for_text("Optimise les performances de mon API", max_vram_mb=20000)
        assert decision is not None
        assert decision.confidence > 0

    def test_recommend_for_text_debug(self):
        router = AdaptiveRouter()
        decision = router.recommend_for_text("Debug le module d'authentification")
        assert decision is not None

    def test_recommend_for_text_chat(self):
        router = AdaptiveRouter()
        decision = router.recommend_for_text("Discutons de l'architecture")
        assert decision is not None

    def test_get_decision_history(self):
        router = AdaptiveRouter()
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        router.recommend(task)
        router.recommend(task)
        history = router.get_decision_history()
        assert len(history) >= 2

    def test_never_recommends_the_embedding_only_model(self):
        """nomic-embed-text serves /api/embed, not /api/chat — Ollama
        returns 400 Bad Request if a task executor tries to chat with it.
        It has the smallest VRAM footprint of all twelve real models
        (0.3GB), so with every other ranking signal at its untrained
        neutral default it won every recommendation before chat_capable
        existed — found by actually running a mission end to end, not by
        a unit test, which is exactly why this one exists now."""
        router = AdaptiveRouter()
        for description in ("Analyze requirements", "Write tests",
                            "Document the solution", "Design solution architecture"):
            decision = router.recommend_for_text(description, max_vram_mb=20000)
            assert decision.model_id != "nomic-embed-text", description
            assert "nomic-embed-text" not in [a["model_id"] for a in decision.alternatives]

    def test_fallback_also_excludes_the_embedding_only_model(self):
        """_fallback_decision has the same smallest-VRAM-wins logic as the
        main path and is just as reachable (e.g. every candidate filtered
        out by max_latency_ms) — it needs the same exclusion."""
        router = AdaptiveRouter()
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_latency_ms=1)
        decision = router._fallback_decision(task)  # noqa: SLF001 - exercising the fallback directly
        assert decision.model_id != "nomic-embed-text"

    def test_recommend_with_alternatives(self):
        router = AdaptiveRouter()
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_vram_mb=20000)
        decision = router.recommend(task)
        assert len(decision.alternatives) > 0

    def test_infer_task_type(self):
        router = AdaptiveRouter()
        assert router._infer_task_type("Write a Python script") == TaskType.CODE_GENERATION
        assert router._infer_task_type("Review this PR") == TaskType.CODE_REVIEW
        assert router._infer_task_type("Fix this bug") == TaskType.DEBUG
        assert router._infer_task_type("Refactor this code") == TaskType.REFACTOR
        assert router._infer_task_type("Analyze performance") == TaskType.ANALYSIS

    def test_infer_complexity(self):
        router = AdaptiveRouter()
        assert router._infer_complexity("Hi") == 0.3
        assert router._infer_complexity("word " * 20) == 0.5
        assert router._infer_complexity("word " * 40) == 0.8


# ═══════════════════════════════════════════════════════════════
# Benchmark Scheduler Tests
# ═══════════════════════════════════════════════════════════════

class TestBenchmarkScheduler:
    def test_run_benchmark(self):
        scheduler = BenchmarkScheduler()
        result = scheduler.run_benchmark("qwen3-coder:30b", TaskType.CODE_GENERATION)
        assert result.quality_score > 0

    def test_run_benchmark_unknown_model(self):
        scheduler = BenchmarkScheduler()
        with pytest.raises(ValueError):
            scheduler.run_benchmark("nonexistent", TaskType.CODE_GENERATION)

    def test_run_full_benchmark(self):
        scheduler = BenchmarkScheduler()
        results = scheduler.run_full_benchmark([TaskType.CODE_GENERATION])
        assert len(results) > 0

    def test_get_latest_benchmarks(self):
        scheduler = BenchmarkScheduler()
        benchmarks = scheduler.get_latest_benchmarks()
        assert len(benchmarks) > 0

    def test_get_regressions(self):
        scheduler = BenchmarkScheduler()
        regressions = scheduler.get_regressions()
        assert isinstance(regressions, list)

    def test_start_stop(self):
        scheduler = BenchmarkScheduler()
        scheduler.start(interval_h=24)
        assert scheduler._running is True
        scheduler.stop()
        assert scheduler._running is False


# ═══════════════════════════════════════════════════════════════
# Runtime Optimizer Tests
# ═══════════════════════════════════════════════════════════════

class TestModelRuntimeOptimizer:
    def test_optimize(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(
            model_id="test", name="Test", parameters_b=7.0,
            vram_required_mb=5000, tokens_per_second=50.0,
            task_scores={"code_generation": 0.9},
            available_backends=[RuntimeBackend.OLLAMA, RuntimeBackend.LLAMACPP],
        )
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        optimizations = optimizer.optimize(profile, task, system_vram_mb=8192)
        assert len(optimizations) > 0

    def test_get_best(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(
            model_id="test", name="Test", parameters_b=7.0,
            vram_required_mb=5000, tokens_per_second=50.0,
            task_scores={"code_generation": 0.9},
            available_backends=[RuntimeBackend.OLLAMA],
        )
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        best = optimizer.get_best(profile, task, system_vram_mb=8192)
        assert best is not None
        assert best.score > 0

    def test_get_best_no_gpu(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(
            model_id="test", name="Test", parameters_b=7.0,
            vram_required_mb=5000, tokens_per_second=50.0,
            task_scores={"code_generation": 0.9},
            available_backends=[RuntimeBackend.KTRANSFORMERS, RuntimeBackend.OLLAMA],
        )
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        best = optimizer.get_best(profile, task, system_vram_mb=8192, has_gpu=False)
        assert best is not None
        assert best.runtime != RuntimeBackend.KTRANSFORMERS

    def test_optimization_to_dict(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(
            model_id="test", name="Test", parameters_b=3.0,
            vram_required_mb=2000, tokens_per_second=80.0,
            task_scores={"code_generation": 0.7},
            available_backends=[RuntimeBackend.OLLAMA],
        )
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        optimizations = optimizer.optimize(profile, task)
        if optimizations:
            d = optimizations[0].to_dict()
            assert "model_id" in d
            assert "runtime" in d

    def test_get_history(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(
            model_id="test", name="Test", parameters_b=3.0,
            vram_required_mb=2000, tokens_per_second=80.0,
            task_scores={"code_generation": 0.7},
            available_backends=[RuntimeBackend.OLLAMA],
        )
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        optimizer.optimize(profile, task)
        history = optimizer.get_optimization_history()
        assert len(history) > 0


# ═══════════════════════════════════════════════════════════════
# API Routes Tests
# ═══════════════════════════════════════════════════════════════

class TestAPIRoutes:
    def test_get_intelligence(self):
        result = handle_get_intelligence()
        assert result["success"] is True
        assert "total_models" in result["data"]

    def test_get_ranking_default(self):
        result = handle_get_ranking()
        assert result["success"] is True
        assert len(result["models"]) > 0

    def test_get_ranking_with_task(self):
        result = handle_get_ranking(task_type="code_generation", limit=3)
        assert result["success"] is True
        assert len(result["models"]) <= 3

    def test_recommend(self):
        result = handle_recommend("Create a REST API", max_vram_mb=20000)
        assert result["success"] is True
        assert "decision" in result

    def test_recommend_small_vram(self):
        result = handle_recommend("Write a Python script", max_vram_mb=4000)
        assert result["success"] is True

    def test_get_history(self):
        handle_recommend("Test task", max_vram_mb=20000)
        result = handle_get_history()
        assert result["success"] is True

    def test_run_benchmark(self):
        result = handle_run_benchmark("qwen3-coder:30b", "code_generation")
        assert result["success"] is True
        assert "benchmark" in result

    def test_run_benchmark_all(self):
        result = handle_run_benchmark()
        assert result["success"] is True

    def test_get_performance(self):
        result = handle_get_performance()
        assert result["success"] is True

    def test_get_performance_specific(self):
        result = handle_get_performance("qwen3-coder:30b")
        assert result["success"] is True
        assert "score" in result

    def test_get_knowledge_without_task_type(self):
        result = handle_get_knowledge()
        assert result["success"] is True
        assert "stats" in result
        assert "best_model_for_task" not in result

    def test_get_knowledge_with_task_type_no_data_yet(self):
        """A task type nothing has ever recorded a real outcome for must
        return None, not a guess — the same "never fabricate" discipline
        as everywhere else this session touched Model Intelligence. Uses a
        task type nothing else in this module-global singleton could ever
        plausibly have recorded, since handle_get_knowledge() reads the
        same shared cache every test in this class does."""
        result = handle_get_knowledge(task_type="__test_isolation_probe_43a__")
        assert result["success"] is True
        assert result["best_model_for_task"] is None

    def test_get_knowledge_reflects_real_usage(self):
        from backend.model_intelligence.routes import _get_memory

        task_type = "__test_isolation_probe_43b__"
        _get_memory().record_model_for_task("qwen3-coder:30b", task_type, True)
        result = handle_get_knowledge(task_type=task_type)
        assert result["success"] is True
        assert any(r["source"] == "qwen3-coder:30b" for r in result["relations"])

    def test_get_evolution_no_underperformers_yet(self):
        result = handle_get_evolution()
        assert result["success"] is True
        assert isinstance(result["underperforming"], list)
        assert "suggestion" not in result

    def test_get_evolution_detects_a_real_underperformer(self):
        """Fabricate the *record*, not the *detection*: feed real-shaped
        performance records (same shape _make_task_executor's on_execution
        hook feeds after a real execution) into an isolated profiler/adapter
        pair and confirm detect_underperforming_models() — not this test —
        is what decides the model is struggling. Isolated rather than
        routed through the module-global singleton other tests in this
        class also share, so this needs no assumption about what state
        those left behind."""
        from backend.model_intelligence.model_evolution_adapter import (
            ModelEvolutionAdapter,
        )
        from backend.model_intelligence.model_intelligence_models import (
            ModelPerformanceRecord,
            TaskType,
        )
        from backend.model_intelligence.model_profiler import ModelProfiler

        profiler = ModelProfiler()
        model_id = next(iter(profiler.list_profiles())).model_id
        for _ in range(5):
            profiler.update_performance(ModelPerformanceRecord(
                model_id=model_id, task_type=TaskType.GENERAL,
                duration_ms=1000, tokens_used=10, success=False,
            ))

        adapter = ModelEvolutionAdapter(profiler=profiler)
        underperforming = adapter.detect_underperforming_models(threshold=0.9)
        assert any(m["model_id"] == model_id for m in underperforming)

    def test_get_evolution_suggestion_stays_within_declared_scope(self):
        """suggest_model_replacement() must never reach into
        PerformanceAnalyzer's benchmark summaries (BenchmarkScheduler's
        simulated numbers) — only ModelProfiler's real, execution-fed
        data. A candidate list keyed only by profile scores is the
        observable proof; get_evolution_summary()'s benchmark-tainted
        model_trends field must not leak in."""
        from backend.model_intelligence.routes import _get_profiler

        profiles = list(_get_profiler().list_profiles())
        result = handle_get_evolution(suggest_for=profiles[0].model_id)
        assert "suggestion" in result
        if result["suggestion"] is not None:
            assert "model_trends" not in result["suggestion"]
            assert "candidates" in result["suggestion"]


# ═══════════════════════════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_profiler_access(self):
        profiler = ModelProfiler()
        errors = []
        def access(n):
            try:
                profiler.list_profiles()
                profiler.get_profile("qwen3-coder:30b")
                profiler.get_stats()
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=access, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_concurrent_router_recommendations(self):
        router = AdaptiveRouter()
        errors = []
        def recommend(n):
            try:
                task = TaskContext(task_type=TaskType.CODE_GENERATION)
                router.recommend(task)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=recommend, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        history = router.get_decision_history()
        assert len(history) >= 10

    def test_concurrent_benchmark_scheduler(self):
        scheduler = BenchmarkScheduler()
        errors = []
        def benchmark(n):
            try:
                scheduler.run_benchmark("qwen3:1.7b", TaskType.CHAT)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=benchmark, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_concurrent_performance_updates(self):
        profiler = ModelProfiler()
        errors = []
        def update(n):
            try:
                profiler.update_performance(ModelPerformanceRecord(
                    model_id="qwen3-coder:30b", task_type=TaskType.CODE_GENERATION,
                    duration_ms=100, tokens_used=50, success=n % 2 == 0,
                ))
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=update, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        stats = profiler.get_stats()
        assert stats["total_runs"] >= 20

    def test_concurrent_runtime_optimizer(self):
        optimizer = ModelRuntimeOptimizer()
        profile = ModelProfile(model_id="test", name="Test", parameters_b=7.0,
                              vram_required_mb=5000, tokens_per_second=50.0,
                              task_scores={"code_generation": 0.9},
                              available_backends=[RuntimeBackend.OLLAMA])
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        errors = []
        def optimize(n):
            try:
                optimizer.optimize(profile, task)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=optimize, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_concurrent_predictor(self):
        predictor = ModelPredictor()
        profile = ModelProfile(model_id="test", name="Test", tokens_per_second=50.0,
                              vram_required_mb=4000, task_scores={"code_generation": 0.9})
        task = TaskContext(task_type=TaskType.CODE_GENERATION)
        errors = []
        def predict(n):
            try:
                predictor.predict_latency(profile, task)
                predictor.predict_tokens_per_second(profile, task)
                predictor.predict_success_probability(profile, [], task)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=predict, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
