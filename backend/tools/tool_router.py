"""Tool router — automatic tool selection for mission/agent contexts (HOS-049)."""

from __future__ import annotations

import threading
from typing import Optional

from .tool_models import ToolCategory, ToolDefinition, ToolPermission, ToolType
from .tool_registry import ToolRegistry


class ToolRouter:
    """Selects the best tool for a given mission/agent/skill context.

    Scoring considers:
    - Category match (mission → tool category)
    - Permission level sufficiency
    - Tool health/availability
    - Historical usage (future: Knowledge Graph integration)
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._category_map: dict[str, ToolCategory] = {
            "github": ToolCategory.VCS,
            "gitlab": ToolCategory.VCS,
            "git": ToolCategory.VCS,
            "docker": ToolCategory.CONTAINER,
            "container": ToolCategory.CONTAINER,
            "database": ToolCategory.DATA,
            "sql": ToolCategory.DATA,
            "data": ToolCategory.DATA,
            "file": ToolCategory.FILE,
            "filesystem": ToolCategory.FILE,
            "api": ToolCategory.NETWORK,
            "rest": ToolCategory.NETWORK,
            "http": ToolCategory.NETWORK,
            "browser": ToolCategory.BROWSER,
            "web": ToolCategory.BROWSER,
            "system": ToolCategory.SYSTEM,
            "shell": ToolCategory.SYSTEM,
        }

    def select(
        self,
        action: str = "",
        context: Optional[dict] = None,
        permission: ToolPermission = ToolPermission.READ,
        preferred_type: Optional[ToolType] = None,
    ) -> tuple[Optional[ToolDefinition], str, float]:
        """Select the best tool. Returns (tool, justification, confidence)."""
        with self._lock:
            category = self._infer_category(action, context or {})
            candidates = self._registry.list_by_category(category)
            available = [t for t in candidates if t.status != "disabled" and t.status != "unavailable"]

            if not available:
                # Fallback: any available tool
                all_available = self._registry.list_available()
                if not all_available:
                    return None, "No tools available", 0.0
                best = self._score_best(all_available, permission, preferred_type)
                return best[0], f"Fallback: {best[1]}", round(best[2] * 0.5, 4)

            # Filter by type preference
            if preferred_type:
                typed = [t for t in available if t.tool_type == preferred_type]
                if typed:
                    available = typed

            best = self._score_best(available, permission, preferred_type)
            return best

    def _infer_category(self, action: str, context: dict) -> ToolCategory:
        action_lower = action.lower()

        # Context override
        if "category" in context:
            cat = context["category"]
            if isinstance(cat, ToolCategory):
                return cat
            if cat in {c.value for c in ToolCategory}:
                return ToolCategory(cat)

        # Action keyword matching
        for keyword, category in self._category_map.items():
            if keyword in action_lower:
                return category

        # Context hints
        if "git" in str(context).lower():
            return ToolCategory.VCS
        if any(k in str(context).lower() for k in ("docker", "container")):
            return ToolCategory.CONTAINER
        if any(k in str(context).lower() for k in ("db", "sql", "database")):
            return ToolCategory.DATA

        return ToolCategory.SYSTEM

    def _score_best(
        self,
        tools: list[ToolDefinition],
        permission: ToolPermission,
        preferred_type: Optional[ToolType],
    ) -> tuple[Optional[ToolDefinition], str, float]:
        if not tools:
            return None, "No tools", 0.0

        best_score = -1.0
        best_tool = None
        best_reason = ""

        for tool in tools:
            score = 0.5  # base

            # Type preference bonus
            if preferred_type and tool.tool_type == preferred_type:
                score += 0.3

            # Permission match penalty
            if permission == ToolPermission.ADMIN and ToolPermission.ADMIN in tool.permissions:
                score += 0.1
            elif permission == ToolPermission.WRITE and ToolPermission.WRITE in tool.permissions:
                score += 0.1
            elif permission == ToolPermission.READ:
                score += 0.1  # base read is fine

            # Health bonus
            if tool.status == "available":
                score += 0.1

            if score > best_score:
                best_score = score
                best_tool = tool
                best_reason = f"Type: {tool.tool_type.value}, Category: {tool.category.value}, Score: {round(score, 2)}"

        return best_tool, best_reason, min(1.0, best_score)

    def stats(self) -> dict:
        with self._lock:
            return {"category_map_size": len(self._category_map)}
