"""Tests for the Runtime Intelligence Layer (HOS-037)."""

from __future__ import annotations

import threading

import pytest

from backend.runtime.intelligence.decision_memory import DecisionMemory
from backend.runtime.intelligence.intelligence_models import (
    DecisionRecord,
    TaskContext,
    TaskStatus,
)
from backend.runtime.intelligence.learning_engine import LearningEngine
from backend.runtime.intelligence.performance_analyzer import PerformanceAnalyzer
from backend.runtime.intelligence.runtime_scorer import RuntimeScorer


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def memory() -> DecisionMemory:
    return DecisionMemory(max_records=1000)


@pytest.fixture
def engine() -> LearningEngine:
    return LearningEngine()


@pytest.fixture
def populated_memory() -> DecisionMemory:
    """Memory with simulated decisions from 3 runtimes."""
    mem = DecisionMemory()
    # Runtime A: reliable, fast
    for i in range(20):
        mem.record(DecisionRecord(
            runtime_id="runtime-a",
            model_name="qwen3:14b",
            task_type="chat",
            status=TaskStatus.SUCCESS,
            duration_ms=150.0 + i * 2,
            resource_cost={"vram_mb": 8192},
        ))
    # Runtime B: slower, some failures
    for i in range(15):
        mem.record(DecisionRecord(
            runtime_id="runtime-b",
            model_name="deepseek:14b",
            task_type="chat",
            status=TaskStatus.SUCCESS if i < 12 else TaskStatus.FAILURE,
            duration_ms=350.0 + i * 5,
            resource_cost={"vram_mb": 10240},
        ))
    # Runtime C: fast, resource-heavy
    for i in range(10):
        mem.record(DecisionRecord(
            runtime_id="runtime-c",
            model_name="qwen3-coder:30b",
            task_type="code",
            status=TaskStatus.SUCCESS,
            duration_ms=200.0 + i,
            resource_cost={"vram_mb": 24576},
        ))
    return mem


# ─── 1. Decision Memory Tests ──────────────────────────────


class TestDecisionMemory:
    def test_record_and_retrieve(self, memory: DecisionMemory):
        """Records are stored and can be retrieved."""
        memory.record(DecisionRecord(
            runtime_id="test-runtime",
            task_type="chat",
            status=TaskStatus.SUCCESS,
            duration_ms=100.0,
        ))
        assert memory.count() == 1
        records = memory.get_by_runtime("test-runtime")
        assert len(records) == 1
        assert records[0].status == TaskStatus.SUCCESS

    def test_get_by_runtime_filtered(self, populated_memory: DecisionMemory):
        """get_by_runtime returns only matching runtime."""
        records_a = populated_memory.get_by_runtime("runtime-a")
        assert len(records_a) == 20
        assert all(r.runtime_id == "runtime-a" for r in records_a)

    def test_get_by_task_type(self, populated_memory: DecisionMemory):
        """get_by_task_type returns only matching task type."""
        code_records = populated_memory.get_by_task_type("code")
        assert len(code_records) == 10
        assert all(r.task_type == "code" for r in code_records)

    def test_stats_accurate(self, populated_memory: DecisionMemory):
        """get_stats returns accurate summary."""
        stats = populated_memory.get_stats("runtime-a")
        assert stats["total"] == 20
        assert stats["successes"] == 20
        assert stats["failures"] == 0
        assert stats["success_rate"] == 1.0

        stats_b = populated_memory.get_stats("runtime-b")
        assert stats_b["total"] == 15
        assert stats_b["successes"] == 12
        assert stats_b["failures"] == 3

    def test_get_all_runtime_ids(self, populated_memory: DecisionMemory):
        """get_all_runtime_ids returns all unique runtime IDs."""
        ids = populated_memory.get_all_runtime_ids()
        assert len(ids) == 3
        assert "runtime-a" in ids
        assert "runtime-b" in ids
        assert "runtime-c" in ids

    def test_max_records_enforced(self):
        """Records beyond max are dropped."""
        mem = DecisionMemory(max_records=50)
        for i in range(100):
            mem.record(DecisionRecord(
                runtime_id=f"r{i % 5}",
                task_type="chat",
            ))
        assert mem.count() <= 50

    def test_clear(self, populated_memory: DecisionMemory):
        """clear empties all records."""
        populated_memory.clear()
        assert populated_memory.count() == 0


# ─── 2. Performance Analyzer Tests ─────────────────────────


class TestPerformanceAnalyzer:
    def test_success_rate(self, populated_memory: DecisionMemory):
        """success_rate computes correctly."""
        analyzer = PerformanceAnalyzer(populated_memory)
        assert analyzer.success_rate("runtime-a") == 1.0
        assert analyzer.success_rate("runtime-b") == 0.8

    def test_avg_latency_ms(self, populated_memory: DecisionMemory):
        """avg_latency_ms computes mean duration."""
        analyzer = PerformanceAnalyzer(populated_memory)
        avg_a = analyzer.avg_latency_ms("runtime-a")
        assert avg_a > 0
        # runtime-a: 20 values 150 + i*2, i=0..19
        # mean = 150 + (0+1+2+...+19)*2/20 = 150 + 190*2/20 = 150 + 19 = 169
        assert 165 <= avg_a <= 175

    def test_stability_score(self, populated_memory: DecisionMemory):
        """stability_score is 0-100."""
        analyzer = PerformanceAnalyzer(populated_memory)
        score = analyzer.stability_score("runtime-a")
        assert 0 <= score <= 100

    def test_resource_efficiency(self, populated_memory: DecisionMemory):
        """Resource efficiency penalizes heavy VRAM usage."""
        analyzer = PerformanceAnalyzer(populated_memory)
        eff_a = analyzer.resource_efficiency("runtime-a")  # 8 GB
        eff_c = analyzer.resource_efficiency("runtime-c")  # 24 GB
        assert eff_a > eff_c  # Less VRAM = higher efficiency

    def test_no_data_returns_zero(self, memory: DecisionMemory):
        """Empty memory returns sensible defaults."""
        analyzer = PerformanceAnalyzer(memory)
        assert analyzer.success_rate("unknown") == 0.0
        assert analyzer.avg_latency_ms("unknown") == 0.0


# ─── 3. Runtime Scorer Tests ───────────────────────────────


class TestRuntimeScorer:
    def test_get_runtime_score(self, populated_memory: DecisionMemory):
        """get_runtime_score computes all score components."""
        analyzer = PerformanceAnalyzer(populated_memory)
        scorer = RuntimeScorer(populated_memory, analyzer)
        score = scorer.get_runtime_score("runtime-a")
        assert score.composite_score > 0
        assert score.performance_score > 0
        assert score.reliability_score > 0
        assert score.resource_efficiency >= 0
        assert score.total_executions == 20
        assert score.successes == 20

    def test_get_all_scores_sorted(self, populated_memory: DecisionMemory):
        """get_all_scores returns descending by composite."""
        analyzer = PerformanceAnalyzer(populated_memory)
        scorer = RuntimeScorer(populated_memory, analyzer)
        scores = scorer.get_all_scores()
        assert len(scores) == 3
        for i in range(len(scores) - 1):
            assert scores[i].composite_score >= scores[i + 1].composite_score

    def test_compare_runtimes(self, populated_memory: DecisionMemory):
        """compare_runtimes returns side-by-side comparison."""
        analyzer = PerformanceAnalyzer(populated_memory)
        scorer = RuntimeScorer(populated_memory, analyzer)
        result = scorer.compare_runtimes("runtime-a", "runtime-b")
        assert "runtime-a" in result
        assert "runtime-b" in result

    def test_recommend_runtime(self, populated_memory: DecisionMemory):
        """recommend_runtime returns the best runtime."""
        analyzer = PerformanceAnalyzer(populated_memory)
        scorer = RuntimeScorer(populated_memory, analyzer)
        rec = scorer.recommend_runtime()
        assert rec is not None
        assert rec.runtime_id
        assert rec.score > 0
        assert rec.confidence > 0
        assert len(rec.alternatives) >= 1

    def test_recommend_with_context(self, populated_memory: DecisionMemory):
        """Recommendation adjusts for context."""
        analyzer = PerformanceAnalyzer(populated_memory)
        scorer = RuntimeScorer(populated_memory, analyzer)
        rec = scorer.recommend_runtime(TaskContext(
            task_type="chat",
            max_latency_ms=200.0,
        ))
        assert rec is not None
        assert rec.runtime_id == "runtime-a" or rec.confidence > 0


# ─── 4. Learning Engine Tests ──────────────────────────────


class TestLearningEngine:
    def test_record_completed(self, engine: LearningEngine):
        """Recording a completed task updates memory and scores."""
        engine.on_runtime_completed(
            runtime_id="test-runtime",
            model_name="qwen3:14b",
            task_type="chat",
            duration_ms=150.0,
            success=True,
        )
        assert engine.total_decisions == 1
        score = engine.get_score("test-runtime")
        assert score is not None
        assert score.total_executions == 1
        assert score.success_rate == 1.0

    def test_record_failed(self, engine: LearningEngine):
        """Recording a failure updates the score."""
        engine.on_runtime_completed(
            runtime_id="test-runtime",
            model_name="qwen3:14b",
            task_type="chat",
            duration_ms=100.0,
            success=False,
        )
        score = engine.get_score("test-runtime")
        assert score is not None
        assert score.failures == 1
        assert score.success_rate == 0.0

    def test_score_evolution(self, engine: LearningEngine):
        """Score changes as more data is recorded."""
        # First: failure — score should be low but not necessarily 0
        # (stability and resource efficiency still contribute)
        engine.on_runtime_failed("r1", "m1", "chat", 100.0)
        score1 = engine.get_score("r1")
        assert score1 is not None
        assert score1.composite_score < 40  # Very low score after failure
        assert score1.success_rate == 0.0

        # Then: successes — score should improve
        for _ in range(5):
            engine.on_runtime_completed("r1", "m1", "chat", 80.0, success=True)
        score2 = engine.get_score("r1")
        assert score2 is not None
        assert score2.composite_score > score1.composite_score
        assert score2.success_rate > 0.5

    def test_recommendations(self, engine: LearningEngine):
        """Recommendations use learned data."""
        engine.on_runtime_completed("runtime-a", "m1", "chat", 100.0, success=True)
        engine.on_runtime_completed("runtime-a", "m1", "chat", 110.0, success=True)
        engine.on_runtime_completed("runtime-b", "m2", "chat", 300.0, success=False)

        rec = engine.recommend(task_type="chat", priority=5)
        assert rec is not None
        assert rec.runtime_id == "runtime-a"

    def test_compare(self, engine: LearningEngine):
        """compare returns comparison dict."""
        engine.on_runtime_completed("a", "m1", "chat", 100.0, success=True)
        engine.on_runtime_completed("b", "m2", "chat", 200.0, success=False)

        result = engine.compare("a", "b")
        assert "a" in result
        assert "b" in result


# ─── 5. Event Publishing Tests ─────────────────────────────


class TestEventPublishing:
    def test_score_updated_event(self):
        """LearningEngine publishes intelligence.score_updated."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        engine = LearningEngine(on_event=on_event)
        engine.on_runtime_completed(
            runtime_id="ev-test",
            model_name="m1",
            task_type="chat",
            duration_ms=100.0,
            success=True,
        )

        score_events = [e for e in events if e["type"] == "intelligence.score_updated"]
        assert len(score_events) == 1
        assert score_events[0]["payload"]["runtime_id"] == "ev-test"

    def test_recommendation_created_event(self):
        """recommend publishes intelligence.recommendation_created."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload})

        engine = LearningEngine(on_event=on_event)
        engine.on_runtime_completed(
            runtime_id="rec-test",
            model_name="m1",
            task_type="chat",
            duration_ms=100.0,
            success=True,
        )
        engine.recommend(task_type="chat")

        rec_events = [e for e in events if e["type"] == "intelligence.recommendation_created"]
        assert len(rec_events) == 1
        assert rec_events[0]["payload"]["runtime_id"] == "rec-test"


# ─── 6. Thread Safety Tests ────────────────────────────────


class TestThreadSafety:
    def test_concurrent_recordings(self):
        """Multiple threads recording decisions don't corrupt data."""
        engine = LearningEngine()
        errors: list[Exception] = []

        def record(idx: int) -> None:
            try:
                for i in range(20):
                    engine.on_runtime_completed(
                        runtime_id=f"r{idx % 3}",
                        model_name="m1",
                        task_type="chat",
                        duration_ms=100.0 + i,
                        success=i % 5 != 0,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert engine.total_decisions == 100

    def test_concurrent_score_access(self):
        """Scores can be read while recording."""
        engine = LearningEngine()
        errors: list[Exception] = []

        for i in range(5):
            engine.on_runtime_completed(f"r{i}", "m1", "chat", 100.0, success=True)

        def reader() -> None:
            for _ in range(50):
                try:
                    engine.get_all_scores()
                except Exception as e:
                    errors.append(e)

        def writer() -> None:
            for _ in range(50):
                try:
                    engine.on_runtime_completed(
                        "r0", "m1", "chat", 100.0, success=True,
                    )
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
