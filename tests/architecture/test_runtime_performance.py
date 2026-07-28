"""HOS-014 sentinel tests — Runtime Performance & Cost Intelligence.

Tests the performance analyzer without any network call or concrete
backend. Events are published manually to a :class:`RuntimeEventBus`.
"""

from __future__ import annotations

import pytest

from backend.ral.runtime_events import (
    RuntimeEvent,
    RuntimeEventBus,
    RuntimeEventType,
    Severity,
)
from backend.ral.runtime_performance import (
    RuntimePerformanceAnalyzer,
    RuntimePerformanceMetrics,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def analyzer() -> RuntimePerformanceAnalyzer:
    bus = RuntimeEventBus(max_events=1000)
    return RuntimePerformanceAnalyzer(bus)


# -----------------------------------------------------------------------------
# Metrics calculation
# -----------------------------------------------------------------------------


def test_metrics_initially_zero(analyzer: RuntimePerformanceAnalyzer) -> None:
    metrics = analyzer.get_metrics("stub")
    assert metrics.runtime_name == "stub"
    assert metrics.executions == 0
    assert metrics.successes == 0
    assert metrics.failures == 0
    assert metrics.fallback_count == 0
    assert metrics.avg_latency_ms == 0.0
    assert metrics.success_rate == 0.0
    assert metrics.reliability_score == 0.0
    assert metrics.performance_score == 0.0
    assert metrics.last_execution is None


def test_started_event_increments_executions(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(
        RuntimeEvent(RuntimeEventType.STARTED, "stub", metadata={"capability": "chat"})
    )
    metrics = analyzer.get_metrics("stub")
    assert metrics.executions == 1
    assert metrics.last_execution is not None


def test_completed_event_increments_successes_and_latency(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
    analyzer.record_event(
        RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 100})
    )
    metrics = analyzer.get_metrics("stub")
    assert metrics.executions == 1
    assert metrics.successes == 1
    assert metrics.failures == 0
    assert metrics.avg_latency_ms == 100.0


def test_failed_event_increments_failures_and_latency(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
    analyzer.record_event(
        RuntimeEvent(RuntimeEventType.FAILED, "stub", severity=Severity.ERROR, metadata={"latency_ms": 50})
    )
    metrics = analyzer.get_metrics("stub")
    assert metrics.executions == 1
    assert metrics.successes == 0
    assert metrics.failures == 1
    assert metrics.avg_latency_ms == 50.0


def test_avg_latency_computed_across_events(analyzer: RuntimePerformanceAnalyzer) -> None:
    for _ in range(2):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
    for latency in (100, 300):
        analyzer.record_event(
            RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": latency})
        )
    metrics = analyzer.get_metrics("stub")
    assert metrics.avg_latency_ms == 200.0


# -----------------------------------------------------------------------------
# Success rate
# -----------------------------------------------------------------------------


def test_success_rate_perfect(analyzer: RuntimePerformanceAnalyzer) -> None:
    for _ in range(4):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "stub"))
    assert analyzer.get_metrics("stub").success_rate == 1.0


def test_success_rate_mixed(analyzer: RuntimePerformanceAnalyzer) -> None:
    for _ in range(3):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "stub"))
    for _ in range(2):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.FAILED, "stub"))
    assert analyzer.get_metrics("stub").success_rate == 0.6


# -----------------------------------------------------------------------------
# Fallback and circuit events
# -----------------------------------------------------------------------------


def test_fallback_count_incremented(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.FALLBACK, "stub"))
    analyzer.record_event(RuntimeEvent(RuntimeEventType.FALLBACK, "stub"))
    assert analyzer.get_metrics("stub").fallback_count == 2


def test_circuit_opened_affects_reliability_score(analyzer: RuntimePerformanceAnalyzer) -> None:
    for _ in range(4):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "stub"))
    analyzer.record_event(RuntimeEvent(RuntimeEventType.CIRCUIT_OPENED, "stub"))
    metrics = analyzer.get_metrics("stub")
    assert metrics.reliability_score < 100.0


def test_recovered_event_recorded(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.RECOVERED, "stub"))
    # RECOVERED does not directly change counters but must not crash.
    assert analyzer.get_metrics("stub").executions == 0


# -----------------------------------------------------------------------------
# Ranking
# -----------------------------------------------------------------------------


def test_rank_runtimes_by_reliability_and_performance(analyzer: RuntimePerformanceAnalyzer) -> None:
    # fast_runtime: low latency, 100% success
    for _ in range(4):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "fast"))
        analyzer.record_event(
            RuntimeEvent(RuntimeEventType.COMPLETED, "fast", metadata={"latency_ms": 10})
        )

    # slow_runtime: higher latency, 100% success
    for _ in range(4):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "slow"))
        analyzer.record_event(
            RuntimeEvent(RuntimeEventType.COMPLETED, "slow", metadata={"latency_ms": 500})
        )

    # flaky_runtime: 50% success, medium latency
    for _ in range(2):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "flaky"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "flaky", metadata={"latency_ms": 100}))
    for _ in range(2):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "flaky"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.FAILED, "flaky"))

    ranked = analyzer.rank_runtimes()
    names = [name for name, _ in ranked]
    assert names == ["fast", "slow", "flaky"]


def test_rank_runtimes_filters_min_executions(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "a"))
    analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "a"))
    for _ in range(5):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "b"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "b"))

    ranked = analyzer.rank_runtimes(min_executions=3)
    assert len(ranked) == 1
    assert ranked[0][0] == "b"


# -----------------------------------------------------------------------------
# get_all_metrics
# -----------------------------------------------------------------------------


def test_get_all_metrics_returns_known_runtimes(analyzer: RuntimePerformanceAnalyzer) -> None:
    analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "alpha"))
    analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "beta"))
    all_metrics = analyzer.get_all_metrics()
    assert set(all_metrics.keys()) == {"alpha", "beta"}
    assert isinstance(all_metrics["alpha"], RuntimePerformanceMetrics)


# -----------------------------------------------------------------------------
# Scores bounded between 0 and 100
# -----------------------------------------------------------------------------


def test_scores_are_bounded(analyzer: RuntimePerformanceAnalyzer) -> None:
    for _ in range(10):
        analyzer.record_event(RuntimeEvent(RuntimeEventType.STARTED, "stub"))
        analyzer.record_event(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 999999}))
    metrics = analyzer.get_metrics("stub")
    assert 0.0 <= metrics.reliability_score <= 100.0
    assert 0.0 <= metrics.performance_score <= 100.0
