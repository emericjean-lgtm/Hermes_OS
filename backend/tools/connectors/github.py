"""GitHub connector abstraction (HOS-049)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.tools.tool_models import ToolRequest, ToolResult, ExecutionStatus


@dataclass
class GitHubRepo:
    owner: str = ""
    name: str = ""
    url: str = ""
    default_branch: str = "main"
    stars: int = 0


@dataclass
class GitHubBranch:
    name: str = ""
    sha: str = ""
    protected: bool = False


@dataclass
class GitHubCommit:
    sha: str = ""
    message: str = ""
    author: str = ""
    date: str = ""


@dataclass
class GitHubPR:
    number: int = 0
    title: str = ""
    state: str = "open"
    author: str = ""
    url: str = ""


@dataclass
class GitHubIssue:
    number: int = 0
    title: str = ""
    state: str = "open"
    labels: list[str] = field(default_factory=list)
    assignee: str = ""


class GitHubConnector:
    """Abstract GitHub connector. Real implementation would use PyGithub or REST API."""

    NAME = "github"
    ACTIONS = ["get_repo", "list_branches", "list_commits", "list_prs", "list_issues",
               "create_branch", "commit", "create_pr", "create_issue"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters

        if action == "get_repo":
            return {"repo": {"owner": params.get("owner", ""), "name": params.get("repo", ""),
                             "url": f"https://github.com/{params.get('owner')}/{params.get('repo')}",
                             "default_branch": "main", "stars": 0}}
        elif action == "list_branches":
            return {"branches": [{"name": "main", "sha": "abc123"}]}
        elif action == "list_commits":
            return {"commits": []}
        elif action == "list_prs":
            return {"pull_requests": []}
        elif action == "list_issues":
            return {"issues": []}
        elif action == "create_branch":
            return {"branch": {"name": params.get("name", "feature"), "from": params.get("from", "main")}}
        elif action == "commit":
            return {"sha": "def456", "message": params.get("message", "")}
        elif action == "create_pr":
            return {"pr": {"number": 1, "title": params.get("title", ""), "state": "open"}}
        elif action == "create_issue":
            return {"issue": {"number": 1, "title": params.get("title", ""), "state": "open"}}
        return {"error": f"Unknown action: {action}"}
