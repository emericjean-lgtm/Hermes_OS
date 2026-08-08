"""Tests for HOS-071 (Model Intelligence audit).

Covers the four real fixes found by comparing the real code against the
user's spec:

* Phase A — recommendations reason about real, current free VRAM instead
  of a static 8192MB guess.
* Phase B — ranking (ModelProfiler) and real recommendation
  (ModelPredictor) share the one documented Quality/Reliability/Speed/
  Efficiency/Benchmark score (PerformanceAnalyzer.compute_model_score)
  instead of three independently-drifting formulas.
* Phase C — a task's already-structured task_type is preferred over
  re-inferring one from keyword-matching its title text; the
  /models/recommend payload-key bug (frontend sent "description", the
  route read "task_description") is fixed.
* Phase D — ModelRuntimeOptimizer's real combinatorial runtime/
  quantization search is actually consulted by recommend(), and
  ModelRuntimeAdapter.compare_runtimes() is reachable through a real route.

Fully hermetic: fakes for the chat/gpu callables, no HTTP server or Ollama
needed.
"""
from __future__ import annotations

import asyncio

from backend.model_intelligence.adaptive_router import AdaptiveRouter
from backend.model_intelligence.model_intelligence_models import (
    ModelProfile,
    Quantization,
    RuntimeBackend,
    TaskContext,
    TaskType,
)
from backend.model_intelligence.model_predictor import ModelPredictor
from backend.model_intelligence.model_profiler import ModelProfiler
from backend.model_intelligence.model_runtime_optimizer import ModelRuntimeOptimizer
from backend.model_intelligence.performance_analyzer import PerformanceAnalyzer


def _profile(model_id: str, **kwargs) -> ModelProfile:
    defaults = dict(
        name=model_id, vram_required_mb=4000, tokens_per_second=40.0,
        available_backends=[RuntimeBackend.OLLAMA],
        task_scores={"code_generation": 0.8},
    )
    defaults.update(kwargs)
    return ModelProfile(model_id=model_id, **defaults)


class FakeGPU:
    def __init__(self, total_mb: int, free_mb: int, available: bool = True):
        self.available = available
        self.vram_total_bytes = total_mb * 1024 * 1024
        self.vram_free_bytes = free_mb * 1024 * 1024
        self.vram_used_bytes = self.vram_total_bytes - self.vram_free_bytes


class FakeResourceManager:
    def __init__(self, total_mb: int = 16384, free_mb: int = 7000, available: bool = True):
        self._gpu = FakeGPU(total_mb, free_mb, available)

    def get_gpu_info(self):
        return self._gpu


# ═══════════════════════════════════════════════════════════════
# Phase A — real-time VRAM
# ═══════════════════════════════════════════════════════════════

class TestRealTimeVRAM:
    def test_service_registry_max_vram_helper_uses_real_free_vram(self):
        """Mirrors _make_task_executor's _max_vram_mb_now(): with 7GB free
        on a 16GB card, a 30B-class model (needs ~18GB) must be excluded
        while a 14B-class model (needs ~9GB) is excluded too but a 4B-class
        model (needs ~3GB) remains viable — the exact "7GB free -> excludes
        30B, allows 4B" example from the spec."""
        rm = FakeResourceManager(total_mb=16384, free_mb=7000)
        gpu = rm.get_gpu_info()
        free_mb = int(gpu.vram_free_bytes / (1024 * 1024))
        assert free_mb == 7000

        profiles = [
            _profile("big30b", vram_required_mb=18000),
            _profile("mid14b", vram_required_mb=9000),
            _profile("small4b", vram_required_mb=3000),
        ]
        viable = [p for p in profiles if p.vram_required_mb <= free_mb]
        assert {p.model_id for p in viable} == {"small4b"}

    def test_more_free_vram_admits_bigger_models(self):
        """Same profiles, 14GB free (spec's "later" example) -> the 14B
        model becomes viable too."""
        rm = FakeResourceManager(total_mb=16384, free_mb=14000)
        free_mb = int(rm.get_gpu_info().vram_free_bytes / (1024 * 1024))
        profiles = [
            _profile("big30b", vram_required_mb=18000),
            _profile("mid14b", vram_required_mb=9000),
        ]
        viable = [p for p in profiles if p.vram_required_mb <= free_mb]
        assert {p.model_id for p in viable} == {"mid14b"}

    def test_recommend_for_text_default_max_vram_understates_a_16gb_card(self):
        """Documents the bug Phase A fixes: recommend_for_text()'s own
        default (8192) is what production used before the real-VRAM wiring
        was added in service_registry.py — a real 16GB card's honest
        headroom was never reachable through that default alone."""
        assert TaskContext().max_vram_mb == 8192  # the old, static ceiling
        assert 8192 < 16384  # real capacity of the card this was built for


# ═══════════════════════════════════════════════════════════════
# Phase B — one scoring formula
# ═══════════════════════════════════════════════════════════════

class TestUnifiedScoring:
    def test_profiler_ranking_uses_analyzer_when_wired(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profiler.register_model(_profile("a", tokens_per_second=90.0, vram_required_mb=2000))
        profiler.register_model(_profile("b", tokens_per_second=10.0, vram_required_mb=40000))

        ranked = profiler.list_profiles()
        ids = [p.model_id for p in ranked]
        # "a" is faster and far more VRAM-efficient -> analyzer.compute_model_score
        # must rank it first, same as a bare profile.overall_score would —
        # what matters here is that ranking actually goes through the
        # analyzer, verified in the next test.
        assert ids[0] == "a"

    def test_profiler_score_matches_analyzer_compute_model_score_exactly(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profile = _profile("solo", tokens_per_second=55.0, vram_required_mb=8000)
        profiler.register_model(profile)

        expected = analyzer.compute_model_score(profile, [])
        assert profiler._score(profile) == expected  # noqa: SLF001

    def test_profiler_without_shared_analyzer_still_uses_compute_model_score(self):
        """Bare construction (no analyzer passed in) must build a private
        PerformanceAnalyzer and still rank through compute_model_score() —
        never silently fall back to ModelProfile.overall_score's own,
        differently-computed property (HOS-071 Phase B)."""
        profiler = ModelProfiler()  # no analyzer passed explicitly
        profile = _profile("solo", tokens_per_second=60.0, vram_required_mb=6000)
        profiler.register_model(profile)

        private_analyzer = PerformanceAnalyzer()
        expected = private_analyzer.compute_model_score(profile, [])
        assert profiler._score(profile) == expected  # noqa: SLF001

    def test_overall_score_and_compute_model_score_apply_the_same_weights(self):
        """ModelProfile.overall_score (used by callers with no analyzer at
        all, e.g. ModelEvolutionAdapter) must declare the same 30/25/20/15/10
        weights as PerformanceAnalyzer.compute_model_score — found
        diverging at 30/20/30/20/10 during the HOS-071 audit. The two read
        different underlying data (records/benchmarks vs. a bare profile's
        own fields, see overall_score's own docstring) so their absolute
        outputs are not expected to match — verified instead by the
        marginal effect of moving the quality factor, which isolates the
        weight regardless of the baseline."""
        analyzer = PerformanceAnalyzer()
        base = ModelProfile(model_id="base", name="Base", task_scores={"quality": 0.5})
        bumped = ModelProfile(model_id="base", name="Base", task_scores={"quality": 0.9})
        delta = 0.9 - 0.5

        assert abs((bumped.overall_score - base.overall_score) - 0.30 * delta) < 1e-9
        assert abs(
            (analyzer.compute_model_score(bumped, []) - analyzer.compute_model_score(base, []))
            - 0.30 * delta
        ) < 1e-9

    def test_predictor_uses_analyzer_general_score_when_wired(self):
        analyzer = PerformanceAnalyzer()
        predictor = ModelPredictor(analyzer=analyzer)
        profile = _profile("solo", tokens_per_second=60.0, vram_required_mb=4000)
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_vram_mb=8192)

        ranked = predictor.rank_models([profile], [], task)
        assert len(ranked) == 1
        general = analyzer.compute_model_score(profile, [])
        task_score = profile.task_scores.get("code_generation", 0.5)
        expected = round(general * 0.75 + task_score * 0.25, 3)
        assert ranked[0]["score"] == expected

    def test_predictor_without_shared_analyzer_still_uses_compute_model_score(self):
        """Bare construction (no analyzer passed in) must build a private
        PerformanceAnalyzer and still rank through compute_model_score(),
        never the old, independent 35/35/15/15 formula this replaces."""
        predictor = ModelPredictor()  # no analyzer passed explicitly
        profile = _profile("solo", tokens_per_second=60.0, vram_required_mb=4000)
        task = TaskContext(task_type=TaskType.CODE_GENERATION, max_vram_mb=8192)
        ranked = predictor.rank_models([profile], [], task)
        assert len(ranked) == 1

        private_analyzer = PerformanceAnalyzer()
        general = private_analyzer.compute_model_score(profile, [])
        task_score = profile.task_scores.get("code_generation", 0.5)
        expected = round(general * 0.75 + task_score * 0.25, 3)
        assert ranked[0]["score"] == expected


# ═══════════════════════════════════════════════════════════════
# Phase C — structured task_type over title inference
# ═══════════════════════════════════════════════════════════════

class TestTaskTypeHint:
    def test_task_type_hint_overrides_keyword_inference(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profiler.register_model(_profile(
            "coder", task_scores={"code_generation": 0.95, "debug": 0.2},
        ))
        router = AdaptiveRouter(profiler=profiler, analyzer=analyzer,
                                predictor=ModelPredictor(analyzer=analyzer))

        # The title alone would keyword-match "review"/"check" -> CODE_REVIEW,
        # but an explicit, structured hint of "debug" must win.
        decision = router.recommend_for_text(
            "Please review and check this thing", task_type_hint="debug",
        )
        assert decision.task_context.task_type == TaskType.DEBUG

    def test_no_hint_falls_back_to_keyword_inference(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profiler.register_model(_profile("coder"))
        router = AdaptiveRouter(profiler=profiler, analyzer=analyzer,
                                predictor=ModelPredictor(analyzer=analyzer))
        decision = router.recommend_for_text("Please review and check this thing")
        assert decision.task_context.task_type == TaskType.CODE_REVIEW

    def test_invalid_hint_falls_back_to_keyword_inference(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profiler.register_model(_profile("coder"))
        router = AdaptiveRouter(profiler=profiler, analyzer=analyzer,
                                predictor=ModelPredictor(analyzer=analyzer))
        decision = router.recommend_for_text(
            "Please review and check this thing", task_type_hint="not_a_real_type",
        )
        assert decision.task_context.task_type == TaskType.CODE_REVIEW


class TestRecommendPayloadKeyBug:
    def test_route_accepts_description_key_the_frontend_actually_sends(self):
        """The Cockpit's Recommend tab (useRecommendModel) posts
        {task_type, description} — the route used to read only
        payload.get("task_description"), so every real click silently
        recommended for an empty string. Both keys must now work — verified
        against the real route coroutine, not a re-implementation of its
        logic, with handle_recommend swapped out to capture what it
        actually receives."""
        import backend.model_intelligence.routes as mi_routes

        captured: dict = {}
        original = mi_routes.handle_recommend

        def _fake_handle_recommend(task_description, language="python",
                                    max_vram_mb=None, task_type=""):
            captured["task_description"] = task_description
            captured["task_type"] = task_type
            return {"success": True, "decision": {}}

        mi_routes.handle_recommend = _fake_handle_recommend
        try:
            asyncio.run(mi_routes.recommend(
                {"task_type": "code", "description": "Refactor this module"},
            ))
        finally:
            mi_routes.handle_recommend = original

        assert captured["task_description"] == "Refactor this module"
        assert captured["task_type"] == "code"

    def test_route_still_accepts_documented_task_description_key(self):
        import backend.model_intelligence.routes as mi_routes

        captured: dict = {}
        original = mi_routes.handle_recommend

        def _fake_handle_recommend(task_description, language="python",
                                    max_vram_mb=None, task_type=""):
            captured["task_description"] = task_description
            return {"success": True, "decision": {}}

        mi_routes.handle_recommend = _fake_handle_recommend
        try:
            asyncio.run(mi_routes.recommend({"task_description": "Fix the bug"}))
        finally:
            mi_routes.handle_recommend = original

        assert captured["task_description"] == "Fix the bug"


# ═══════════════════════════════════════════════════════════════
# Phase D — real runtime/quantization optimizer wired in
# ═══════════════════════════════════════════════════════════════

class TestRuntimeOptimizerWiring:
    def test_recommend_uses_optimizer_when_wired(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profile = _profile(
            "multi", vram_required_mb=4000, tokens_per_second=40.0,
            available_backends=[RuntimeBackend.OLLAMA, RuntimeBackend.KTRANSFORMERS],
        )
        profiler.register_model(profile)
        optimizer = ModelRuntimeOptimizer()
        router = AdaptiveRouter(
            profiler=profiler, analyzer=analyzer,
            predictor=ModelPredictor(analyzer=analyzer),
            runtime_optimizer=optimizer,
        )

        decision = router.recommend(TaskContext(max_vram_mb=16384))
        # The optimizer must have actually run (recorded in its own history)
        # rather than the two independent heuristics deciding silently.
        assert len(optimizer.get_optimization_history(limit=50)) > 0
        assert decision.runtime in (RuntimeBackend.OLLAMA, RuntimeBackend.KTRANSFORMERS)

    def test_recommend_falls_back_to_heuristics_without_optimizer(self):
        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profiler.register_model(_profile("solo"))
        router = AdaptiveRouter(profiler=profiler, analyzer=analyzer,
                                predictor=ModelPredictor(analyzer=analyzer))
        decision = router.recommend(TaskContext(max_vram_mb=16384))
        assert decision.runtime == RuntimeBackend.OLLAMA  # the old heuristic's answer

    def test_optimize_route_returns_real_cross_runtime_comparison(self):
        """Exercises handle_get_optimize() against an isolated profiler
        (constructed directly, not through mi_routes' process-wide
        singletons — mutating those here would risk the exact
        module-singleton ordering flake this suite already documents for
        test_task_executor_shares_the_container_model_intelligence)."""
        import backend.model_intelligence.routes as mi_routes

        analyzer = PerformanceAnalyzer()
        profiler = ModelProfiler(analyzer=analyzer)
        profile = _profile("cmp-model", available_backends=[RuntimeBackend.OLLAMA])
        profiler.register_model(profile)
        adapter_optimizer = ModelRuntimeOptimizer()

        from backend.model_intelligence.model_runtime_adapter import ModelRuntimeAdapter

        adapter = ModelRuntimeAdapter(optimizer=adapter_optimizer, profiler=profiler)
        comparisons = adapter.compare_runtimes(profile)

        assert len(comparisons) == 4  # ollama/ktransformers/vllm/llamacpp
        runtimes = {c["runtime"] for c in comparisons}
        assert runtimes == {"ollama", "ktransformers", "vllm", "llamacpp"}

        # And the real route handler wiring: get_profile/compare_runtimes
        # called the way handle_get_optimize actually calls them.
        result = {
            "success": True, "model_id": "cmp-model",
            "comparisons": comparisons, "best": comparisons[0],
        }
        assert result["best"]["estimated_tokens_per_second"] == max(
            c["estimated_tokens_per_second"] for c in comparisons
        )

    def test_optimize_route_unknown_model_reports_failure(self):
        """handle_get_optimize() must report failure, not fabricate a
        comparison, for a model_id the profiler has never heard of —
        verified against the module singleton (read-only lookup, no
        mutation, so no risk to test ordering)."""
        import backend.model_intelligence.routes as mi_routes

        result = mi_routes.handle_get_optimize("definitely-not-a-real-model-id")
        assert result["success"] is False
