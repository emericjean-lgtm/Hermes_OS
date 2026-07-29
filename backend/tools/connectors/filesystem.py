"""Filesystem connector abstraction (HOS-049)."""

from __future__ import annotations

from typing import Any

from backend.tools.tool_models import ToolRequest


class FilesystemConnector:
    """Abstract filesystem connector with controlled read/write/search."""

    NAME = "filesystem"
    ACTIONS = ["read", "write", "list", "search", "stat"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters
        path = params.get("path", "/")

        if action == "read":
            return {"path": path, "content": "", "size_bytes": 0, "read_only": True}
        elif action == "write":
            return {"path": path, "written": True, "size_bytes": params.get("content", "").__len__()}
        elif action == "list":
            return {"path": path, "entries": [], "count": 0}
        elif action == "search":
            return {"pattern": params.get("pattern", ""), "path": path, "matches": [], "count": 0}
        elif action == "stat":
            return {"path": path, "size_bytes": 0, "is_dir": False, "modified": ""}
        return {"error": f"Unknown action: {action}"}
