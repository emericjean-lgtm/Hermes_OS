"""Browser connector abstraction (HOS-049)."""

from __future__ import annotations

from typing import Any

from backend.tools.tool_models import ToolRequest


class BrowserConnector:
    """Abstract browser connector for navigation, extraction, and screenshots."""

    NAME = "browser"
    ACTIONS = ["navigate", "extract_text", "screenshot", "click", "fill"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters

        if action == "navigate":
            return {"url": params.get("url", ""), "status": "loaded", "title": ""}
        elif action == "extract_text":
            return {"url": params.get("url", ""), "text": "", "selector": params.get("selector", "body")}
        elif action == "screenshot":
            return {"url": params.get("url", ""), "format": "png", "data": ""}
        elif action == "click":
            return {"selector": params.get("selector", ""), "action": "clicked"}
        elif action == "fill":
            return {"selector": params.get("selector", ""), "value": params.get("value", ""), "action": "filled"}
        return {"error": f"Unknown action: {action}"}
