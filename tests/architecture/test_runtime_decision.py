"""HOS-015 sentinel tests — Adaptive Runtime Decision Engine.

Tests the composite decision engine without any network call. Uses a
shared :class:`RuntimeEventBus` connected to the performance analyzer
so the engine can compute scores from real event data.
"""

from __future__ import annotations

import pytest

from backend.ral.adapters.stub_runtime import StubRuntime
from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.runtime_decision import (
    RuntimeDecision,
    RuntimeDecisionEngine,
    RuntimeDecisionError,
    RuntimeDecisionScore,
    RuntimeDecisionWeights,
)
from backend.ral.runtime_events import (
    RuntimeEvent,
    RuntimeEventBus,
    RuntimeEventType,
)
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_health import RuntimeHealthMonitor
from backend.ral.runtime_performance import RuntimePerformanceAnalyzer
from backend.ral.runtime_recovery import RuntimeRecoveryManager
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def bus() -> RuntimeEventBus:
    return RuntimeEventBus(max_events=1000)


@pytest.fixture
def registry() -> RuntimeRegistry:
    return RuntimeRegistry()


@pytest.fixture
def selector(registry: RuntimeRegistry) -> RuntimeSelector:
    return RuntimeSelector(registry)


@pytest.fixture
def health_monitor(registry: RuntimeRegistry) -> RuntimeHealthMonitor:
    return RuntimeHealthMonitor(registry)


@pytest.fixture
def performance_analyzer(bus: RuntimeEventBus) -> RuntimePerformanceAnalyzer:
    return RuntimePerformanceAnalyzer(bus)


@pytest.fixture
def recovery_manager(registry: RuntimeRegistry, selector: RuntimeSelector) -> RuntimeRecoveryManager:
    return RuntimeRecoveryManager(registry, selector, failure_threshold=3)


@pytest.fixture
def engine(
    registry: RuntimeRegistry,
    selector: RuntimeSelector,
    health_monitor: RuntimeHealthMonitor,
    performance_analyzer: RuntimePerformanceAnalyzer,
    recovery_manager: RuntimeRecoveryManager,
) -> RuntimeDecisionEngine:
    return RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
    )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _start_runtime(registry: RuntimeRegistry, name: str, runtime: RuntimeInterface) -> None:
    registry.register(name, runtime)
    await RuntimeLifecycle.initialize(runtime)


def _publish_stats(bus: RuntimeEventBus, name: str, successes: int, failures: int, latencies: list[int]) -> None:
    """Publish started+completed/failed events to prime the performance analyzer."""
    for _ in range(successes):
        bus.publish(RuntimeEvent(RuntimeEventType.STARTED, name))
    for i in range(successes):
        latency = latencies[i] if i < len(latencies) else 100
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, name, metadata={"latency_ms": latency}))
    for _ in range(failures):
        bus.publish(RuntimeEvent(RuntimeEventType.STARTED, name))
        bus.publish(RuntimeEvent(RuntimeEventType.FAILED, name, metadata={"latency_ms": 50}))


# ============================================================================
# Score sanity
# ============================================================================


def test_runtime_decision_weights_defaults() -> None:
    w = RuntimeDecisionWeights()
    assert w.health_weight == 1.0
    assert w.performance_weight == 1.0
    assert w.reliability_weight == 1.0
    assert w.capability_weight == 1.0
    assert w.policy_weight == 1.0
    assert w.circuit_penalty_weight == 1.0


def test_runtime_decision_score_dataclass() -> None:
    s = RuntimeDecisionScore(runtime_name="stub")
    assert s.runtime_name == "stub"
    assert s.final_score == 0.0


def test_runtime_decision_dataclass() -> None:
    d = RuntimeDecision(selected_runtime="stub")
    assert d.selected_runtime == "stub"
    assert d.timestamp > 0


# ============================================================================
# Best runtime selection
# ============================================================================


@pytest.mark.asyncio
async def test_select_best_runtime(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
    health_monitor: RuntimeHealthMonitor,
) -> None:
    stub = StubRuntime()
    await _start_runtime(registry, "stub", stub)

    _publish_stats(bus, "stub", successes=5, failures=0, latencies=[10, 20, 15, 30, 25])

    decision = engine.select_runtime("chat")
    assert decision.selected_runtime == "stub"
    assert decision.confidence > 0
    assert decision.decision_score > 0
    assert len(decision.candidate_scores) > 0
    assert decision.decision_reason != ""


@pytest.mark.asyncio
async def test_select_runtime_no_candidates_raises(engine: RuntimeDecisionEngine) -> None:
    with pytest.raises(RuntimeDecisionError, match="No candidate runtime"):
        engine.select_runtime("chat")


@pytest.mark.asyncio
async def test_select_runtime_min_confidence_not_met(
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    stub = StubRuntime()
    registry.register("stub", stub)
    # stub is not started → health_score = 0
    with pytest.raises(RuntimeDecisionError, match="minimum confidence"):
        engine.select_runtime("chat", min_confidence=0.5)


# ============================================================================
# Runtime evaluation
# ============================================================================


@pytest.mark.asyncio
async def test_evaluate_unregistered_runtime(engine: RuntimeDecisionEngine) -> None:
    with pytest.raises(RuntimeDecisionError, match="is not registered"):
        engine.evaluate_runtime("nonexistent", "chat")


@pytest.mark.asyncio
async def test_evaluate_healthy_runtime(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    stub = StubRuntime()
    await _start_runtime(registry, "stub", stub)
    _publish_stats(bus, "stub", successes=4, failures=0, latencies=[10, 20, 15, 25])

    score = engine.evaluate_runtime("stub", "chat")
    assert score.runtime_name == "stub"
    assert score.health_score > 0
    assert score.capability_score > 0
    assert score.final_score > 0


# ============================================================================
# Performance and reliability influence
# ============================================================================


@pytest.mark.asyncio
async def test_performance_influence(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    fast = StubRuntime()
    slow = StubRuntime()
    await _start_runtime(registry, "fast", fast)
    await _start_runtime(registry, "slow", slow)

    # fast: low latency, 100% success
    _publish_stats(bus, "fast", successes=5, failures=0, latencies=[5, 10, 8, 12, 7])
    # slow: high latency, 100% success
    _publish_stats(bus, "slow", successes=5, failures=0, latencies=[800, 900, 750, 850, 950])

    decision = engine.select_runtime("chat")
    assert decision.selected_runtime == "fast"


@pytest.mark.asyncio
async def test_reliability_influence(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    reliable = StubRuntime()
    flaky = StubRuntime()
    await _start_runtime(registry, "reliable", reliable)
    await _start_runtime(registry, "flaky", flaky)

    # reliable: 100% success, medium latency
    _publish_stats(bus, "reliable", successes=5, failures=0, latencies=[100, 100, 100, 100, 100])
    # flaky: 50% success, low latency
    _publish_stats(bus, "flaky", successes=3, failures=3, latencies=[10, 10, 10])

    decision = engine.select_runtime("chat")
    assert decision.selected_runtime == "reliable"


# ============================================================================
# Circuit breaker influence
# ============================================================================


@pytest.mark.asyncio
async def test_circuit_open_penalises_runtime(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    selector: RuntimeSelector,
    health_monitor: RuntimeHealthMonitor,
    performance_analyzer: RuntimePerformanceAnalyzer,
    recovery_manager: RuntimeRecoveryManager,
) -> None:
    good = StubRuntime()
    broken = StubRuntime()
    await _start_runtime(registry, "good", good)
    await _start_runtime(registry, "broken", broken)

    _publish_stats(bus, "good", successes=5, failures=0, latencies=[30, 30, 30, 30, 30])
    _publish_stats(bus, "broken", successes=3, failures=0, latencies=[5, 5, 5])

    # Open the circuit for 'broken'
    recovery_manager.record_failure("broken", RuntimeError("boom"))
    recovery_manager.record_failure("broken", RuntimeError("boom"))
    recovery_manager.record_failure("broken", RuntimeError("boom"))

    engine = RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
    )

    decision = engine.select_runtime("chat")
    assert decision.selected_runtime == "good"


# ============================================================================
# Custom weights
# ============================================================================


@pytest.mark.asyncio
async def test_custom_weights_change_selection(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    selector: RuntimeSelector,
    health_monitor: RuntimeHealthMonitor,
    performance_analyzer: RuntimePerformanceAnalyzer,
    recovery_manager: RuntimeRecoveryManager,
) -> None:
    perf = StubRuntime()
    reliable = StubRuntime()
    await _start_runtime(registry, "perf", perf)
    await _start_runtime(registry, "reliable", reliable)

    # perf: low latency, but very unreliable (2/7 successes ≈ 29%)
    _publish_stats(bus, "perf", successes=2, failures=5, latencies=[3, 2])
    # reliable: high latency, but 100% success
    _publish_stats(bus, "reliable", successes=5, failures=0, latencies=[700, 720, 690, 710, 730])

    # Default weights: reliable wins (reliability ceiling 250 > performance ceiling 200)
    engine_default = RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
    )
    default_decision = engine_default.select_runtime("chat")
    assert default_decision.selected_runtime == "reliable"

    # Custom weights: heavy performance weight → perf wins
    perf_weights = RuntimeDecisionWeights(performance_weight=10.0)
    engine_perf = RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
        weights=perf_weights,
    )
    perf_decision = engine_perf.select_runtime("chat")
    assert perf_decision.selected_runtime == "perf"


# ============================================================================
# Explanation
# ============================================================================


@pytest.mark.asyncio
async def test_explain_decision(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    stub = StubRuntime()
    await _start_runtime(registry, "stub", stub)
    _publish_stats(bus, "stub", successes=3, failures=0, latencies=[10, 20, 15])

    decision = engine.select_runtime("chat")
    explanation = decision.decision_reason
    assert "Selected runtime" in explanation
    assert "stub" in explanation
    assert "Scores:" in explanation


# ============================================================================
# Ranking
# ============================================================================


@pytest.mark.asyncio
async def test_rank_candidates_order(
    bus: RuntimeEventBus,
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    a = StubRuntime()
    b = StubRuntime()
    await _start_runtime(registry, "a", a)
    await _start_runtime(registry, "b", b)

    _publish_stats(bus, "a", successes=3, failures=0, latencies=[10, 10, 10])
    _publish_stats(bus, "b", successes=3, failures=3, latencies=[100, 100, 100])

    ranked = engine.rank_candidates("chat")
    assert len(ranked) >= 2
    assert ranked[0].runtime_name == "a"
    assert ranked[-1].runtime_name == "b"


# ============================================================================
# Thread safety
# ============================================================================


@pytest.mark.asyncio
async def test_engine_thread_safety(
    registry: RuntimeRegistry,
    engine: RuntimeDecisionEngine,
) -> None:
    """Weight changes must not corrupt concurrent evaluations."""
    stub = StubRuntime()
    await _start_runtime(registry, "stub", stub)

    import threading
    errors: list[Exception] = []

    def set_weights() -> None:
        for _ in range(50):
            engine.set_weights(RuntimeDecisionWeights(health_weight=0.5))

    def evaluate() -> None:
        for _ in range(50):
            try:
                engine.evaluate_runtime("stub", "chat")
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=set_weights)
    t2 = threading.Thread(target=evaluate)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety violations: {errors}"


# ============================================================================
# Score ties
# ============================================================================


def test_runtime_decision_score_frozen() -> None:
    s = RuntimeDecisionScore(runtime_name="test", final_score=42.0)
    assert s.final_score == 42.0
    with pytest.raises(AttributeError):
        s.final_score = 99.0  # type: ignore[misc]


def test_set_weights_updates() -> None:
    w = RuntimeDecisionWeights(health_weight=2.0)
    assert w.health_weight == 2.0
