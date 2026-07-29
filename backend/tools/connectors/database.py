"""Database connector abstraction (PostgreSQL + SQLite) (HOS-049)."""

from __future__ import annotations

from typing import Any

from backend.tools.tool_models import ToolRequest


class DatabaseConnector:
    """Abstract database connector. Supports PostgreSQL and SQLite."""

    NAME = "database"
    ACTIONS = ["schema_inspect", "query", "list_tables"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters
        db_type = params.get("db_type", "sqlite")

        if action == "schema_inspect":
            return {"tables": [], "db_type": db_type, "database": params.get("database", "")}
        elif action == "query":
            return {"columns": [], "rows": [], "row_count": 0,
                    "query": params.get("query", ""), "limited": True}
        elif action == "list_tables":
            return {"tables": [], "db_type": db_type}
        return {"error": f"Unknown action: {action}"}
