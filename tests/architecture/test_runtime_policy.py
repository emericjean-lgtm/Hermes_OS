"""HOS-016 sentinel tests — Runtime Policy Engine.

Tests the policy engine and its integration with RuntimeDecisionEngine.
No concrete backend is contacted; all data is in-memory.
"""

from __future__ import annotations

import threading

import pytest

from backend.ral.adapters.stub_runtime import StubRuntime
from backend.ral.runtime_decision import (
    RuntimeDecisionEngine,
    RuntimeDecisionError,
)
from backend.ral.runtime_events import RuntimeEventBus, RuntimeEvent, RuntimeEventType
from backend.ral.runtime_factory import RuntimeLifecycle
from backend.ral.runtime_health import RuntimeHealthMonitor
from backend.ral.runtime_performance import RuntimePerformanceAnalyzer
from backend.ral.runtime_policy import (
    RuntimeExecutionContext,
    RuntimePolicy,
    RuntimePolicyEngine,
    RuntimePolicyError,
    RuntimePolicyResult,
    RuntimePolicyRule,
)
from backend.ral.runtime_recovery import RuntimeRecoveryManager
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_selector import RuntimeSelector


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def policy_engine() -> RuntimePolicyEngine:
    return RuntimePolicyEngine()


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
def bus() -> RuntimeEventBus:
    return RuntimeEventBus()


@pytest.fixture
def performance_analyzer(bus: RuntimeEventBus) -> RuntimePerformanceAnalyzer:
    return RuntimePerformanceAnalyzer(bus)


@pytest.fixture
def recovery_manager(registry: RuntimeRegistry, selector: RuntimeSelector) -> RuntimeRecoveryManager:
    return RuntimeRecoveryManager(registry, selector)


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


# ============================================================================
# Policy dataclasses
# ============================================================================


def test_runtime_policy_rule_defaults() -> None:
    rule = RuntimePolicyRule()
    assert rule.allowed_runtimes is None
    assert rule.denied_runtimes is None


def test_runtime_policy_construction() -> None:
    policy = RuntimePolicy(
        name="test-policy",
        enabled=True,
        priority=10,
        description="Test policy",
        rules=(
            RuntimePolicyRule(denied_runtimes=frozenset({"ollama"})),
        ),
    )
    assert policy.name == "test-policy"
    assert policy.priority == 10
    assert len(policy.rules) == 1


def test_runtime_policy_result_defaults() -> None:
    result = RuntimePolicyResult()
    assert result.allowed is True
    assert result.rejected_reason is None


def test_runtime_execution_context_defaults() -> None:
    ctx = RuntimeExecutionContext()
    assert ctx.capability == ""


# ============================================================================
# Policy engine: register / remove / list / clear
# ============================================================================


def test_register_policy(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(name="main", rules=(RuntimePolicyRule(),))
    policy_engine.register_policy(policy)
    assert len(policy_engine.list_policies()) == 1


def test_register_policy_overwrites(policy_engine: RuntimePolicyEngine) -> None:
    policy_engine.register_policy(RuntimePolicy(name="x", rules=(RuntimePolicyRule(),)))
    policy_engine.register_policy(RuntimePolicy(name="x", priority=5, rules=(RuntimePolicyRule(),)))
    pols = policy_engine.list_policies()
    assert len(pols) == 1
    assert pols[0].priority == 5


def test_register_policy_no_rules_raises(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(name="empty", rules=())
    with pytest.raises(RuntimePolicyError, match="has no rules"):
        policy_engine.register_policy(policy)


def test_remove_policy(policy_engine: RuntimePolicyEngine) -> None:
    policy_engine.register_policy(RuntimePolicy(name="a", rules=(RuntimePolicyRule(),)))
    policy_engine.remove_policy("a")
    assert len(policy_engine.list_policies()) == 0


def test_remove_nonexistent_raises(policy_engine: RuntimePolicyEngine) -> None:
    with pytest.raises(RuntimePolicyError, match="is not registered"):
        policy_engine.remove_policy("nonexistent")


def test_clear(policy_engine: RuntimePolicyEngine) -> None:
    policy_engine.register_policy(RuntimePolicy(name="a", rules=(RuntimePolicyRule(),)))
    policy_engine.register_policy(RuntimePolicy(name="b", rules=(RuntimePolicyRule(),)))
    policy_engine.clear()
    assert policy_engine.list_policies() == []


# ============================================================================
# Evaluation: basic rules
# ============================================================================


def test_evaluate_default_allow(policy_engine: RuntimePolicyEngine) -> None:
    ctx = RuntimeExecutionContext(capability="chat")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True
    assert result.policy_name == ""
    assert result.applied_rules == 0


def test_evaluate_denied_runtime(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="deny-ollama",
        rules=(RuntimePolicyRule(denied_runtimes=frozenset({"ollama"})),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", runtime_name="ollama")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False
    assert "denied" in (result.rejected_reason or "")


def test_evaluate_allowed_runtime(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="allow-stub",
        rules=(RuntimePolicyRule(allowed_runtimes=frozenset({"stub"})),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", runtime_name="stub")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True


def test_evaluate_runtime_not_in_allowed_set(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="allow-stub",
        rules=(RuntimePolicyRule(allowed_runtimes=frozenset({"stub"})),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", runtime_name="ollama")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False


# ============================================================================
# Evaluation: constraints (local, cloud, confidential)
# ============================================================================


def test_evaluate_local_only_pass(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="local-only",
        rules=(RuntimePolicyRule(local_only=True),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", provider="local")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True


def test_evaluate_local_only_fail_cloud(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="local-only",
        rules=(RuntimePolicyRule(local_only=True),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", provider="cloud-ollama")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False


def test_evaluate_confidential_required(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="confidential",
        rules=(RuntimePolicyRule(confidential=True),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", confidential=True)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True


def test_evaluate_confidential_fail(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="confidential",
        rules=(RuntimePolicyRule(confidential=True),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", confidential=False)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False


# ============================================================================
# Evaluation: latency and reliability thresholds
# ============================================================================


def test_evaluate_max_latency_pass(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="low-latency",
        rules=(RuntimePolicyRule(max_latency_ms=100.0),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", avg_latency_ms=50.0)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True


def test_evaluate_max_latency_fail(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="low-latency",
        rules=(RuntimePolicyRule(max_latency_ms=100.0),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", avg_latency_ms=200.0)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False


def test_evaluate_min_reliability_pass(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="reliable",
        rules=(RuntimePolicyRule(min_reliability=80.0),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", reliability=95.0)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True


def test_evaluate_min_reliability_fail(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="reliable",
        rules=(RuntimePolicyRule(min_reliability=80.0),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", reliability=50.0)
    result = policy_engine.evaluate(ctx)
    assert result.allowed is False


# ============================================================================
# Evaluation: preferences
# ============================================================================


def test_evaluate_preferred_runtime(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="prefer-local",
        rules=(RuntimePolicyRule(preferred_runtime="stub"),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat")
    result = policy_engine.evaluate(ctx)
    assert result.preferred_runtime == "stub"


def test_evaluate_preferred_provider(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(
        name="prefer-local",
        rules=(RuntimePolicyRule(preferred_provider="local"),),
    )
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat")
    result = policy_engine.evaluate(ctx)
    assert result.preferred_provider == "local"


# ============================================================================
# Evaluation: priority and conflicts
# ============================================================================


def test_high_priority_wins(policy_engine: RuntimePolicyEngine) -> None:
    low = RuntimePolicy(name="low", priority=1, rules=(RuntimePolicyRule(
        preferred_runtime="stub",
    ),))
    high = RuntimePolicy(name="high", priority=10, rules=(RuntimePolicyRule(
        denied_runtimes=frozenset({"stub"}),
    ),))
    policy_engine.register_policy(low)
    policy_engine.register_policy(high)

    ctx = RuntimeExecutionContext(capability="chat", runtime_name="stub")
    result = policy_engine.evaluate(ctx)
    # High-priority policy denies stub
    assert result.allowed is False


def test_disabled_policy_is_skipped(policy_engine: RuntimePolicyEngine) -> None:
    policy = RuntimePolicy(name="deny", enabled=False, rules=(RuntimePolicyRule(
        denied_runtimes=frozenset({"stub"}),
    ),))
    policy_engine.register_policy(policy)

    ctx = RuntimeExecutionContext(capability="chat", runtime_name="stub")
    result = policy_engine.evaluate(ctx)
    assert result.allowed is True  # no enabled policy matches


# ============================================================================
# Integration with RuntimeDecisionEngine
# ============================================================================


@pytest.mark.asyncio
async def test_policy_denies_runtime(
    registry: RuntimeRegistry,
    selector: RuntimeSelector,
    health_monitor: RuntimeHealthMonitor,
    bus: RuntimeEventBus,
    performance_analyzer: RuntimePerformanceAnalyzer,
    recovery_manager: RuntimeRecoveryManager,
) -> None:
    stub = StubRuntime()
    registry.register("stub", stub)
    await RuntimeLifecycle.initialize(stub)
    bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 10}))
    bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "stub", metadata={"latency_ms": 10}))

    policy_engine = RuntimePolicyEngine()
    policy_engine.register_policy(RuntimePolicy(
        name="deny-stub",
        rules=(RuntimePolicyRule(denied_runtimes=frozenset({"stub"})),),
    ))

    engine = RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
        policy_engine=policy_engine,
    )

    with pytest.raises(RuntimeDecisionError, match="No candidate runtime"):
        engine.select_runtime("chat")


@pytest.mark.asyncio
async def test_policy_preferred_runtime_wins(
    registry: RuntimeRegistry,
    selector: RuntimeSelector,
    health_monitor: RuntimeHealthMonitor,
    bus: RuntimeEventBus,
    performance_analyzer: RuntimePerformanceAnalyzer,
    recovery_manager: RuntimeRecoveryManager,
) -> None:
    a = StubRuntime()
    b = StubRuntime()
    registry.register("alpha", a)
    registry.register("beta", b)
    await RuntimeLifecycle.initialize(a)
    await RuntimeLifecycle.initialize(b)
    for _ in range(3):
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "alpha", metadata={"latency_ms": 10}))
        bus.publish(RuntimeEvent(RuntimeEventType.COMPLETED, "beta", metadata={"latency_ms": 10}))

    policy_engine = RuntimePolicyEngine()
    policy_engine.register_policy(RuntimePolicy(
        name="prefer-beta",
        rules=(RuntimePolicyRule(preferred_runtime="beta"),),
    ))

    engine = RuntimeDecisionEngine(
        registry=registry,
        selector=selector,
        health_monitor=health_monitor,
        performance_analyzer=performance_analyzer,
        recovery_manager=recovery_manager,
        policy_engine=policy_engine,
    )

    decision = engine.select_runtime("chat")
    assert decision.selected_runtime == "beta"


# ============================================================================
# Thread safety
# ============================================================================


def test_policy_engine_thread_safety(policy_engine: RuntimePolicyEngine) -> None:
    errors: list[Exception] = []

    def register() -> None:
        for i in range(50):
            policy_engine.register_policy(RuntimePolicy(
                name=f"p{i}", rules=(RuntimePolicyRule(),),
            ))

    def evaluate() -> None:
        for _ in range(50):
            try:
                ctx = RuntimeExecutionContext(capability="chat")
                policy_engine.evaluate(ctx)
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=register)
    t2 = threading.Thread(target=evaluate)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread safety violations: {errors}"
