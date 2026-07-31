"""Evolution Scheduler for Hermes OS (HOS-058).

Internal cron for periodic evolution cycles:
- Hourly: Quick analysis
- Daily: Optimization report
- Weekly: Deep analysis
"""

from __future__ import annotations

import threading
import time
from typing import Any

from .evolution_models import EvolutionReport, EvolutionStatus, SystemMetrics


class EvolutionScheduler:
    """Internal cron scheduler for periodic evolution analysis.

    Modes:
    - hourly: quick metrics check
    - daily: full analysis + optimization report
    - weekly: deep analysis with pattern discovery
    """

    def __init__(self, engine: Any, run_immediate: bool = False) -> None:
        self._engine = engine
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._hourly_count = 0
        self._daily_count = 0
        self._weekly_count = 0

        if run_immediate:
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def run_hourly(self) -> list[dict]:
        """Quick analysis: check current metrics for critical issues."""
        metrics = self._generate_sample_metrics()
        results = self._engine.run_full_pipeline(metrics)
        self._hourly_count += 1
        return results

    def run_daily(self) -> EvolutionReport:
        """Daily: full analysis + generate optimization report."""
        metrics = self._generate_sample_metrics()
        self._engine.run_full_pipeline(metrics)
        report = self._engine.generate_report()
        self._daily_count += 1
        return report

    def run_weekly(self) -> dict[str, Any]:
        """Weekly: deep analysis with pattern discovery."""
        metrics = self._generate_sample_metrics(complex_mode=True)
        self._engine.run_full_pipeline(metrics)
        report = self._engine.generate_report()
        self._weekly_count += 1

        # Pattern discovery
        patterns_discovered = 0
        proposals = self._engine.get_proposals(EvolutionStatus.APPLIED)
        for p in proposals[-5:]:
            if p.expected_gain > 10:
                patterns_discovered += 1

        return {
            "report": report,
            "patterns_discovered": patterns_discovered,
            "weekly_gain": sum(p.expected_gain for p in proposals if p.status == EvolutionStatus.APPLIED),
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "hourly_runs": self._hourly_count,
                "daily_runs": self._daily_count,
                "weekly_runs": self._weekly_count,
            }

    def _run_loop(self) -> None:
        """Background thread that runs analysis on a schedule."""
        # Simulated: hourly = 60s, daily = 5min, weekly = 15min (shortened for testing)
        hourly_interval = 60  # 1 min
        daily_interval = 300  # 5 min
        weekly_interval = 900  # 15 min
        start = time.time()

        while self._running:
            elapsed = time.time() - start

            if elapsed >= weekly_interval:
                self.run_weekly()
                start = time.time()
            elif elapsed >= daily_interval:
                self.run_daily()
                time.sleep(5)
            elif elapsed >= hourly_interval:
                self.run_hourly()
                time.sleep(5)
            else:
                time.sleep(10)

    @staticmethod
    def _generate_sample_metrics(complex_mode: bool = False) -> SystemMetrics:
        """Generate sample system metrics for analysis."""
        import random
        return SystemMetrics(
            runtime_avg_latency_ms=random.uniform(200, 800) if complex_mode else 450.0,
            runtime_vram_mb=random.uniform(1024, 8192) if complex_mode else 4096.0,
            runtime_error_rate=random.uniform(0.01, 0.20) if complex_mode else 0.05,
            runtime_model_score=random.uniform(0.3, 0.9) if complex_mode else 0.75,
            agent_success_rate=random.uniform(0.5, 0.95) if complex_mode else 0.82,
            agent_avg_duration_ms=random.uniform(2000, 15000) if complex_mode else 5000.0,
            agent_failure_count=random.randint(0, 20) if complex_mode else 3,
            skill_usage_rate=random.uniform(0.3, 0.9) if complex_mode else 0.6,
            skill_success_rate=random.uniform(0.5, 0.95) if complex_mode else 0.8,
            skill_unused_ratio=random.uniform(0.1, 0.7) if complex_mode else 0.3,
            mission_avg_duration_s=random.uniform(30, 300) if complex_mode else 120.0,
            mission_blocked_count=random.randint(0, 15) if complex_mode else 2,
            mission_repeat_rate=random.uniform(0.1, 0.5) if complex_mode else 0.2,
            memory_pattern_count=random.randint(50, 500) if complex_mode else 200,
            memory_hit_rate=random.uniform(0.3, 0.9) if complex_mode else 0.65,
            memory_prune_rate=random.uniform(0.05, 0.4) if complex_mode else 0.15,
        )
