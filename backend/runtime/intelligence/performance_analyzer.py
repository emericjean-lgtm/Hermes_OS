"""Performance Analyzer for the Runtime Intelligence Layer (HOS-037).

Computes success rates, latency stats, and stability metrics.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.runtime.intelligence.decision_memory import DecisionMemory
from backend.runtime.intelligence.intelligence_models import TaskStatus


class PerformanceAnalyzer:
    """Analyzes runtime performance from decision history."""

    def __init__(self, memory: DecisionMemory) -> None:
        self._memory = memory

    # ── Success Rate ───────────────────────────────────────

    def success_rate(self, runtime_id: str) -> float:
        """Ratio of successful executions."""
        stats = self._memory.get_stats(runtime_id)
        return stats["success_rate"]

    def success_rate_weighted(
        self,
        runtime_id: str,
        recent_weight: float = 0.7,
    ) -> float:
        """Weighted success rate emphasizing recent executions."""
        records = self._memory.get_by_runtime(runtime_id)
        if not records:
            return 0.0

        total = len(records)
        split = max(1, int(total * (1 - recent_weight)))
        recent = records[-split:] if split > 0 else records
        older = records[:-split] if split < total else []

        r_success = sum(1 for r in recent if r.status == TaskStatus.SUCCESS)
        r_total = len(recent)
        recent_rate = r_success / r_total if r_total > 0 else 0.0

        if older:
            o_success = sum(1 for r in older if r.status == TaskStatus.SUCCESS)
            o_total = len(older)
            older_rate = o_success / o_total if o_total > 0 else 0.0
            return recent_weight * recent_rate + (1 - recent_weight) * older_rate
        return recent_rate

    # ── Latency ────────────────────────────────────────────

    def avg_latency_ms(self, runtime_id: str) -> float:
        """Mean execution duration."""
        stats = self._memory.get_stats(runtime_id)
        return stats["avg_duration_ms"]

    def latency_stddev_ms(self, runtime_id: str) -> float:
        """Standard deviation of execution duration (stability)."""
        records = self._memory.get_by_runtime(runtime_id)
        if len(records) < 2:
            return 0.0

        mean = self.avg_latency_ms(runtime_id)
        variance = sum((r.duration_ms - mean) ** 2 for r in records) / len(records)
        return math.sqrt(variance)

    # ── Stability ──────────────────────────────────────────

    def stability_score(self, runtime_id: str) -> float:
        """Score based on latency consistency. Lower stddev = higher stability."""
        records = self._memory.get_by_runtime(runtime_id)
        if not records:
            return 0.0

        mean = self.avg_latency_ms(runtime_id)
        if mean == 0:
            return 100.0

        stddev = self.latency_stddev_ms(runtime_id)
        cv = stddev / mean  # Coefficient of variation
        # Normalize: 0 → 100, 2.0 → 0
        score = max(0.0, 100.0 * (1.0 - min(cv, 2.0) / 2.0))
        return round(score, 2)

    # ── Resource Efficiency ────────────────────────────────

    def resource_efficiency(self, runtime_id: str) -> float:
        """How efficiently the runtime uses resources."""
        records = self._memory.get_by_runtime(runtime_id)
        if not records:
            return 0.0

        # Penalize heavy resource usage
        total_vram = 0
        count = 0
        for r in records:
            vram = r.resource_cost.get("vram_mb", 0)
            if vram > 0:
                total_vram += vram
                count += 1

        if count == 0:
            return 50.0  # Neutral

        avg_vram = total_vram / count
        # Score: 16 GB = 100, 0 GB = 100 (small models good), penalize mid-range
        # Simpler: lower VRAM → better score
        score = max(0.0, 100.0 - (avg_vram / 1024 / 16 * 100))
        return round(score, 2)
