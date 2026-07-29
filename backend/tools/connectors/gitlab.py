"""GitLab connector abstraction (HOS-049)."""

from __future__ import annotations

from typing import Any

from backend.tools.tool_models import ToolRequest


class GitLabConnector:
    """Abstract GitLab connector. Real implementation would use python-gitlab or REST API."""

    NAME = "gitlab"
    ACTIONS = ["get_project", "list_branches", "list_commits", "list_mrs", "list_issues",
               "create_branch", "commit", "create_mr", "create_issue"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters

        if action == "get_project":
            return {"project": {"id": params.get("project_id", ""),
                                "name": params.get("project", ""),
                                "web_url": f"https://gitlab.com/{params.get('project')}"}}
        elif action == "list_branches":
            return {"branches": [{"name": "main", "commit": {"id": "abc123"}}]}
        elif action == "list_commits":
            return {"commits": []}
        elif action == "list_mrs":
            return {"merge_requests": []}
        elif action == "list_issues":
            return {"issues": []}
        elif action == "create_branch":
            return {"branch": {"name": params.get("name", "feature")}}
        elif action == "commit":
            return {"id": "def456"}
        elif action == "create_mr":
            return {"iid": 1, "title": params.get("title", ""), "state": "opened"}
        elif action == "create_issue":
            return {"iid": 1, "title": params.get("title", ""), "state": "opened"}
        return {"error": f"Unknown action: {action}"}
