"""Tool memory integration — feeds Knowledge Graph with tool usage data (HOS-049)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from .tool_models import ExecutionStatus, ToolDefinition, ToolRequest, ToolResult


class ToolMemory:
    """Records tool usage into the Knowledge Graph for later retrieval.

    Relationships stored:
    Agent → Tool → Mission → Result → Performance → Experience
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._usage: list[dict] = []

    def record(
        self,
        request: ToolRequest,
        result: ToolResult,
        tool: ToolDefinition,
    ) -> dict:
        """Record a tool execution for memory/graph integration."""
        entry = {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "tool_type": tool.tool_type.value,
            "action": request.action,
            "agent_id": request.agent_id,
            "mission_id": request.mission_id,
            "status": result.status.value,
            "duration_ms": result.duration_ms,
            "success": result.status == ExecutionStatus.COMPLETED,
            "error": result.error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            self._usage.append(entry)
            if len(self._usage) > 5000:
                self._usage = self._usage[-5000:]

        return entry

    def query(self, tool_id: Optional[str] = None, agent_id: Optional[str] = None,
              mission_id: Optional[str] = None, success_only: bool = False,
              limit: int = 50) -> list[dict]:
        with self._lock:
            results = self._usage

            if tool_id:
                results = [r for r in results if r["tool_id"] == tool_id]
            if agent_id:
                results = [r for r in results if r["agent_id"] == agent_id]
            if mission_id:
                results = [r for r in results if r["mission_id"] == mission_id]
            if success_only:
                results = [r for r in results if r["success"]]

            return results[-limit:]

    def get_tool_stats(self, tool_id: str) -> dict:
        with self._lock:
            entries = [r for r in self._usage if r["tool_id"] == tool_id]
            if not entries:
                return {"tool_id": tool_id, "total": 0}

            success = [r for r in entries if r["success"]]
            return {
                "tool_id": tool_id,
                "total": len(entries),
                "success_count": len(success),
                "success_rate": round(len(success) / len(entries), 4),
                "avg_duration_ms": round(sum(r["duration_ms"] for r in entries) / len(entries), 2),
                "last_used": max(r["timestamp"] for r in entries),
            }

    def get_agent_stats(self, agent_id: str) -> dict:
        with self._lock:
            entries = [r for r in self._usage if r["agent_id"] == agent_id]
            if not entries:
                return {"agent_id": agent_id, "total": 0}

            tools_used = set(r["tool_id"] for r in entries)
            return {
                "agent_id": agent_id,
                "total": len(entries),
                "tools_used": len(tools_used),
                "favorite_tool": max(tools_used, key=lambda tid: sum(1 for r in entries if r["tool_id"] == tid)),
            }

    def stats(self) -> dict:
        with self._lock:
            total = len(self._usage)
            if total == 0:
                return {"total": 0, "success_rate": 0.0}
            success = sum(1 for r in self._usage if r["success"])
            tools = set(r["tool_id"] for r in self._usage)
            agents = set(r["agent_id"] for r in self._usage if r["agent_id"])
            return {
                "total": total,
                "success_rate": round(success / total, 4),
                "unique_tools": len(tools),
                "unique_agents": len(agents),
            }
