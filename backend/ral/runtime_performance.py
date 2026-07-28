"""Runtime Abstraction Layer — runtime performance & cost intelligence (HOS-014).

Provides in-memory analysis of runtime performance, reliability and cost
traits derived from the event stream produced by HOS-013.

No external backend is contacted. All data is kept in memory and is
intentionally lost on process restart.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from backend.ral.runtime_events import RuntimeEvent, RuntimeEventBus, RuntimeEventType


@dataclass(frozen=True)
class RuntimePerformanceMetrics:
    """Performance, reliability and cost snapshot for a single runtime.

    Attributes:
        runtime_name: Identifier of the runtime.
        executions: Total number of execution attempts.
        successes: Number of successful executions.
        failures: Number of failed executions.
        fallback_count: Number of times this runtime triggered a fallback.
        avg_latency_ms: Average execution latency in milliseconds.
        success_rate: Ratio of successes over executions (0.0-1.0).
        reliability_score: Aggregated reliability score (0-100).
        performance_score: Aggregated performance score (0-100).
        last_execution: Unix timestamp of the last execution, or ``None``.
    """

    runtime_name: str
    executions: int = 0
    successes: int = 0
    failures: int = 0
    fallback_count: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 0.0
    reliability_score: float = 0.0
    performance_score: float = 0.0
    last_execution: float | None = None


class RuntimePerformanceAnalyzer:
    """Analyze runtime events and produce per-runtime performance metrics.

    The analyzer subscribes to a :class:`RuntimeEventBus` and maintains
    rolling counters per runtime. Scores are derived on demand so the
    latest values are always consistent with the current data.

    Args:
        event_bus: The bus to observe.
    """

    def __init__(self, event_bus: RuntimeEventBus) -> None:
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._executions: dict[str, int] = defaultdict(int)
        self._successes: dict[str, int] = defaultdict(int)
        self._failures: dict[str, int] = defaultdict(int)
        self._fallbacks: dict[str, int] = defaultdict(int)
        self._recoveries: dict[str, int] = defaultdict(int)
        self._circuit_opens: dict[str, int] = defaultdict(int)
        self._latency_total_ms: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._last_execution: dict[str, float] = {}
        event_bus.subscribe(self.record_event)

    def record_event(self, event: RuntimeEvent) -> None:
        """Process a single event and update internal counters."""
        name = event.runtime_name
        event_type = event.event_type

        with self._lock:
            if event_type == RuntimeEventType.STARTED:
                self._executions[name] += 1
                self._last_execution[name] = event.timestamp

            elif event_type == RuntimeEventType.COMPLETED:
                self._successes[name] += 1
                latency = event.metadata.get("latency_ms", 0)
                if isinstance(latency, (int, float)) and latency >= 0:
                    self._latency_total_ms[name] += latency
                    self._latency_count[name] += 1

            elif event_type == RuntimeEventType.FAILED:
                self._failures[name] += 1
                latency = event.metadata.get("latency_ms", 0)
                if isinstance(latency, (int, float)) and latency >= 0:
                    self._latency_total_ms[name] += latency
                    self._latency_count[name] += 1

            elif event_type == RuntimeEventType.FALLBACK:
                self._fallbacks[name] += 1

            elif event_type == RuntimeEventType.RECOVERED:
                self._recoveries[name] += 1

            elif event_type == RuntimeEventType.CIRCUIT_OPENED:
                self._circuit_opens[name] += 1

    def get_metrics(self, runtime_name: str) -> RuntimePerformanceMetrics:
        """Return the current performance metrics for ``runtime_name``.

        Args:
            runtime_name: Runtime identifier.

        Returns:
            A :class:`RuntimePerformanceMetrics` instance.
        """
        with self._lock:
            return self._calculate_metrics(runtime_name)

    def get_all_metrics(self) -> dict[str, RuntimePerformanceMetrics]:
        """Return a mapping from runtime name to metrics for every known runtime.

        A runtime is considered "known" as soon as at least one event has
        been recorded for it.
        """
        with self._lock:
            names = set(self._executions) | set(self._successes) | set(self._failures)
            return {name: self._calculate_metrics(name) for name in names}

    def rank_runtimes(
        self,
        *,
        min_executions: int = 0,
    ) -> list[tuple[str, RuntimePerformanceMetrics]]:
        """Rank runtimes by descending reliability, then performance score.

        Args:
            min_executions: Filter out runtimes with fewer executions.

        Returns:
            A list of ``(runtime_name, metrics)`` tuples, sorted from
            best to worst according to the composite ranking.
        """
        with self._lock:
            metrics = self.get_all_metrics()
            ranked = [
                (name, m)
                for name, m in metrics.items()
                if m.executions >= min_executions
            ]
            return sorted(
                ranked,
                key=lambda item: (item[1].reliability_score, item[1].performance_score),
                reverse=True,
            )

    def _calculate_metrics(self, runtime_name: str) -> RuntimePerformanceMetrics:
        """Compute metrics for ``runtime_name`` assuming the lock is held."""
        executions = self._executions[runtime_name]
        successes = self._successes[runtime_name]
        failures = self._failures[runtime_name]
        fallbacks = self._fallbacks[runtime_name]
        circuit_opens = self._circuit_opens[runtime_name]

        latency_count = self._latency_count[runtime_name]
        avg_latency = (
            self._latency_total_ms[runtime_name] / latency_count
            if latency_count
            else 0.0
        )

        success_rate = successes / executions if executions else 0.0

        reliability_score = self._reliability_score(
            success_rate, circuit_opens, fallbacks, executions
        )
        performance_score = self._performance_score(
            avg_latency, successes, failures, executions
        )

        return RuntimePerformanceMetrics(
            runtime_name=runtime_name,
            executions=executions,
            successes=successes,
            failures=failures,
            fallback_count=fallbacks,
            avg_latency_ms=avg_latency,
            success_rate=success_rate,
            reliability_score=reliability_score,
            performance_score=performance_score,
            last_execution=self._last_execution.get(runtime_name),
        )

    @staticmethod
    def _reliability_score(
        success_rate: float,
        circuit_opens: int,
        fallbacks: int,
        executions: int,
    ) -> float:
        """Return a reliability score between 0 and 100."""
        base = success_rate * 100.0
        # Penalize circuit openings and fallbacks, with caps to avoid
        # collapsing a runtime that has only started once.
        circuit_penalty = min(circuit_opens * 10, 30.0)
        fallback_penalty = min(fallbacks * 5, 20.0)
        # Small usage bonus: a runtime with many executions is considered
        # more battle-tested, up to a modest cap.
        usage_bonus = min(executions * 0.5, 5.0)
        score = base - circuit_penalty - fallback_penalty + usage_bonus
        return max(0.0, min(100.0, score))

    @staticmethod
    def _performance_score(
        avg_latency_ms: float,
        successes: int,
        failures: int,
        executions: int,
    ) -> float:
        """Return a performance score between 0 and 100.

        The score rewards low latency and penalizes instability.
        If no executions have been recorded, the score is 0.
        """
        if executions == 0:
            return 0.0

        # Latency score: 100 at 0ms, decreasing by 1 point per 10ms.
        latency_score = max(0.0, 100.0 - avg_latency_ms / 10.0)

        # Stability penalty based on failure ratio.
        total = successes + failures
        if total > 0:
            failure_ratio = failures / total
            stability_penalty = failure_ratio * 20.0
        else:
            stability_penalty = 0.0

        score = latency_score - stability_penalty
        return max(0.0, min(100.0, score))
