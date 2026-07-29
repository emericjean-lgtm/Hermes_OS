"""Execution Context Manager for the Agent Supervisor (HOS-043).

Manages execution contexts for task dispatch and tracking.
"""

from __future__ import annotations

import threading
from typing import Optional

from backend.agents.agent_models import ExecutionContext


class ExecutionContextManager:
    """Thread-safe manager for execution contexts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._contexts: dict[str, ExecutionContext] = {}
        self._by_agent: dict[str, list[str]] = {}
        self._by_mission: dict[str, list[str]] = {}

    def create_context(
        self,
        agent_id: str,
        mission_id: str,
        node_id: str,
        task_title: str = "",
        task_description: str = "",
        task_type: str = "task",
        preferred_runtime: str = "",
        preferred_model: str = "",
        benchmark_profile: str = "",
        estimated_vram_gb: float = 0.0,
        estimated_ram_gb: float = 0.0,
        estimated_tokens: int = 0,
        max_retries: int = 3,
        timeout_seconds: float = 300.0,
        priority: str = "normal",
    ) -> ExecutionContext:
        """Create a new execution context."""
        ctx = ExecutionContext(
            agent_id=agent_id,
            mission_id=mission_id,
            node_id=node_id,
            task_title=task_title,
            task_description=task_description,
            task_type=task_type,
            preferred_runtime=preferred_runtime,
            preferred_model=preferred_model,
            benchmark_profile=benchmark_profile,
            estimated_vram_gb=estimated_vram_gb,
            estimated_ram_gb=estimated_ram_gb,
            estimated_tokens=estimated_tokens,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        with self._lock:
            self._contexts[ctx.context_id] = ctx
            self._by_agent.setdefault(agent_id, []).append(ctx.context_id)
            self._by_mission.setdefault(mission_id, []).append(ctx.context_id)
        return ctx

    def get(self, context_id: str) -> Optional[ExecutionContext]:
        with self._lock:
            return self._contexts.get(context_id)

    def get_by_agent(self, agent_id: str) -> list[ExecutionContext]:
        with self._lock:
            ctx_ids = self._by_agent.get(agent_id, [])
            return [self._contexts[cid] for cid in ctx_ids if cid in self._contexts]

    def get_by_mission(self, mission_id: str) -> list[ExecutionContext]:
        with self._lock:
            ctx_ids = self._by_mission.get(mission_id, [])
            return [self._contexts[cid] for cid in ctx_ids if cid in self._contexts]

    def increment_retry(self, context_id: str) -> bool:
        with self._lock:
            ctx = self._contexts.get(context_id)
            if ctx is None:
                return False
            ctx.retry_count += 1
            return True

    def remove(self, context_id: str) -> bool:
        with self._lock:
            ctx = self._contexts.pop(context_id, None)
            if ctx is None:
                return False
            if ctx.agent_id in self._by_agent:
                self._by_agent[ctx.agent_id] = [
                    c for c in self._by_agent[ctx.agent_id] if c != context_id
                ]
            if ctx.mission_id in self._by_mission:
                self._by_mission[ctx.mission_id] = [
                    c for c in self._by_mission[ctx.mission_id] if c != context_id
                ]
            return True

    def count_active(self) -> int:
        with self._lock:
            return len(self._contexts)
