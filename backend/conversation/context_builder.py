"""Context Builder for Hermes OS (HOS-064).

Builds conversation context from active missions, agents, runtime,
and memory state to inform AI responses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .conversation_models import ConversationContext


class ContextBuilder:
    """Builds enriched conversation context from Hermes OS state."""

    def __init__(self) -> None:
        self._memory_manager: Any = None
        self._mission_planner: Any = None
        self._agent_supervisor: Any = None

    def set_memory_manager(self, mm: Any) -> None:
        self._memory_manager = mm

    def set_mission_planner(self, mp: Any) -> None:
        self._mission_planner = mp

    def set_agent_supervisor(self, sup: Any) -> None:
        self._agent_supervisor = sup

    def build_context(self, user_message: str,
                      session_context: ConversationContext | None = None,
                      enrich: bool = True) -> ConversationContext:
        ctx = session_context or ConversationContext()

        # Update from active state
        if enrich:
            ctx.active_agents = self._get_active_agents()
            ctx.workspace_status = self._get_workspace_status()
            ctx.security_level = self._get_security_level()

        # Memory enrichment
        if enrich and self._memory_manager:
            try:
                search_result = self._memory_manager.search(
                    user_message[:100], mode="semantic"
                )
                if search_result:
                    ctx.environment_vars["memory_hit"] = "true"
            except Exception:
                pass

        ctx.recent_events = self._get_recent_events(ctx, limit=5)
        ctx.updated_at = datetime.now(timezone.utc).isoformat()
        return ctx

    def build_initial_context(self, user_id: str = "anonymous") -> ConversationContext:
        return ConversationContext(
            active_agents=self._get_active_agents(),
            workspace_status=self._get_workspace_status(),
            security_level=self._get_security_level(),
            recent_events=self._get_recent_events(None, limit=3),
        )

    def update_context(self, session_id: str, updates: dict[str, Any]) -> None:
        """Update context with specific key-value pairs."""
        pass  # Placeholder for context persistence

    # ── Private helpers (mockable) ──

    def _get_active_agents(self) -> list[str]:
        if self._agent_supervisor:
            try:
                agents = self._agent_supervisor.list_agents()
                return [a.agent_id for a in agents
                        if hasattr(a, "agent_id") and a.status == "READY"]
            except Exception:
                pass
        return []

    def _get_workspace_status(self) -> str:
        return "ready"

    def _get_security_level(self) -> str:
        return "normal"

    def _get_recent_events(self, ctx: ConversationContext | None,
                           limit: int = 5) -> list[dict[str, Any]]:
        if ctx and ctx.recent_events:
            return ctx.recent_events[-limit:]
        return []
