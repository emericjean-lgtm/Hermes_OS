"""Thread-safe tool registry (HOS-049)."""

from __future__ import annotations

import threading
from typing import Optional

from .tool_models import ToolCategory, ToolDefinition, ToolStatus, ToolType


class ToolRegistry:
    """Central registry of all tools. Thread-safe with multi-index."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, ToolDefinition] = {}
        self._by_type: dict[ToolType, set[str]] = {t: set() for t in ToolType}
        self._by_category: dict[ToolCategory, set[str]] = {c: set() for c in ToolCategory}
        self._by_status: dict[ToolStatus, set[str]] = {s: set() for s in ToolStatus}
        self._by_tag: dict[str, set[str]] = {}

    # ── CRUD ─────────────────────────────────────────────

    def register(self, tool: ToolDefinition) -> ToolDefinition:
        with self._lock:
            self._tools[tool.id] = tool
            self._index(tool)
            return tool

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        with self._lock:
            return self._tools.get(tool_id)

    def list_all(self) -> list[ToolDefinition]:
        with self._lock:
            return list(self._tools.values())

    def list_by_type(self, tool_type: ToolType) -> list[ToolDefinition]:
        with self._lock:
            ids = self._by_type.get(tool_type, set())
            return [self._tools[sid] for sid in ids if sid in self._tools]

    def list_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        with self._lock:
            ids = self._by_category.get(category, set())
            return [self._tools[sid] for sid in ids if sid in self._tools]

    def list_by_status(self, status: ToolStatus) -> list[ToolDefinition]:
        with self._lock:
            ids = self._by_status.get(status, set())
            return [self._tools[sid] for sid in ids if sid in self._tools]

    def list_available(self) -> list[ToolDefinition]:
        return self.list_by_status(ToolStatus.AVAILABLE)

    def list_by_tag(self, tag: str) -> list[ToolDefinition]:
        with self._lock:
            ids = self._by_tag.get(tag, set())
            return [self._tools[sid] for sid in ids if sid in self._tools]

    def delete(self, tool_id: str) -> bool:
        with self._lock:
            tool = self._tools.pop(tool_id, None)
            if tool is None:
                return False
            self._unindex(tool)
            return True

    def update_status(self, tool_id: str, status: ToolStatus) -> bool:
        with self._lock:
            tool = self._tools.get(tool_id)
            if tool is None:
                return False
            old_status = tool.status
            tool.status = status
            self._by_status[old_status].discard(tool_id)
            self._by_status[status].add(tool_id)
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._tools)

    # ── Index helpers ────────────────────────────────────

    def _index(self, tool: ToolDefinition) -> None:
        self._by_type[tool.tool_type].add(tool.id)
        self._by_category[tool.category].add(tool.id)
        self._by_status[tool.status].add(tool.id)
        for tag in tool.tags:
            self._by_tag.setdefault(tag, set()).add(tool.id)

    def _unindex(self, tool: ToolDefinition) -> None:
        self._by_type[tool.tool_type].discard(tool.id)
        self._by_category[tool.category].discard(tool.id)
        self._by_status[tool.status].discard(tool.id)
        for tag in tool.tags:
            s = self._by_tag.get(tag)
            if s:
                s.discard(tool.id)
                if not s:
                    del self._by_tag[tag]

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._tools),
                "by_type": {t.value: len(ids) for t, ids in self._by_type.items() if ids},
                "by_category": {c.value: len(ids) for c, ids in self._by_category.items() if ids},
                "by_status": {s.value: len(ids) for s, ids in self._by_status.items() if ids},
                "unique_tags": len(self._by_tag),
            }
