"""REST API connector abstraction (HOS-049)."""

from __future__ import annotations

from typing import Any

from backend.tools.tool_models import ToolRequest


class RestAPIConnector:
    """Abstract REST API connector with controlled HTTP methods."""

    NAME = "rest_api"
    ACTIONS = ["get", "post", "put", "delete", "head"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters
        url = params.get("url", "")

        if action not in ("get", "post", "put", "delete", "head"):
            return {"error": f"Unsupported method: {action}", "url": url}

        return {
            "method": action.upper(),
            "url": url,
            "status_code": 200,
            "headers": {},
            "body": {},
            "response_time_ms": 0,
        }
