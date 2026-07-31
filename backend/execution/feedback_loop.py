"""Feedback Loop — analyzes mission outcomes and feeds learnings back into the system."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .execution_models import ExecutionReport, ExecutionState


class FeedbackLoop:
    """Post-mission analysis engine.

    Analyzes: duration, cost, errors, decisions, agents used, models used, tools used.
    Feeds into: Memory, Knowledge Graph, Runtime Intelligence.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reports: dict[str, ExecutionReport] = {}
        self._learnings: list[dict[str, Any]] = []  # Extracted lessons

    def analyze(self, report: ExecutionReport) -> dict[str, Any]:
        """Analyze a completed execution report and extract learnings."""
        with self._lock:
            self._reports[report.execution_id] = report

            learnings = self._extract_learnings(report)
            self._learnings.append({
                "execution_id": report.execution_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "learnings": learnings,
            })

            return {
                "execution_id": report.execution_id,
                "state": report.state.value,
                "efficiency": self._calculate_efficiency(report),
                "learnings": learnings,
                "recommendations": self._generate_recommendations(report, learnings),
            }

    def get_memory_input(self, execution_id: str) -> dict[str, Any]:
        """Get structured data for the Memory Manager integration."""
        with self._lock:
            report = self._reports.get(execution_id)
            if not report:
                return {}
            return {
                "mission_id": report.mission_id,
                "outcome": report.state.value,
                "duration_ms": report.total_duration_ms,
                "agents": report.agents_used,
                "runtimes": report.runtimes_used,
                "skills": report.skills_used,
                "tools": report.tools_used,
                "errors": report.errors,
                "optimizations": report.optimizations,
                "completed_tasks": report.completed_tasks,
                "failed_tasks": report.failed_tasks,
            }

    def get_intelligence_input(self, execution_id: str) -> dict[str, Any]:
        """Get structured data for Runtime Intelligence integration."""
        with self._lock:
            report = self._reports.get(execution_id)
            if not report:
                return {}
            return {
                "execution_id": execution_id,
                "state": report.state.value,
                "runtimes_used": report.runtimes_used,
                "skills_used": report.skills_used,
                "tools_used": report.tools_used,
                "total_duration_ms": report.total_duration_ms,
                "failed_tasks": report.failed_tasks,
            }

    def _extract_learnings(self, report: ExecutionReport) -> list[dict[str, Any]]:
        learnings = []

        if report.state == ExecutionState.COMPLETED:
            learnings.append({"type": "success", "message": f"Mission {report.mission_id} completed successfully."})
        elif report.state == ExecutionState.FAILED:
            learnings.append({"type": "failure", "message": f"Mission {report.mission_id} failed: {report.errors}"})

        if report.failed_tasks > 0:
            learnings.append({
                "type": "warning",
                "message": f"{report.failed_tasks} tasks failed out of {report.total_tasks}",
            })

        if report.optimizations:
            learnings.append({"type": "optimization", "message": f"Optimizations found: {report.optimizations}"})

        return learnings

    def _calculate_efficiency(self, report: ExecutionReport) -> float:
        if report.total_tasks == 0:
            return 0.0
        base = report.completed_tasks / report.total_tasks
        if report.failed_tasks > 0:
            base *= 0.8
        return round(base * 100, 1)

    def _generate_recommendations(self, report: ExecutionReport,
                                   learnings: list[dict[str, Any]]) -> list[str]:
        recs = []
        if report.failed_tasks > report.total_tasks * 0.3:
            recs.append("Consider reviewing task decomposition — high failure rate.")
        if report.total_duration_ms > 600_000:  # > 10 min
            recs.append("Consider runtime optimization — mission duration > 10 min.")
        return recs

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "reports_analyzed": len(self._reports),
                "learnings_extracted": len(self._learnings),
            }
