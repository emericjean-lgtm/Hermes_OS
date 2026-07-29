"""Docker connector abstraction (HOS-049)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.tools.tool_models import ToolRequest


@dataclass
class DockerImage:
    name: str = ""
    tag: str = "latest"
    size_mb: float = 0.0


@dataclass
class DockerContainer:
    id: str = ""
    name: str = ""
    image: str = ""
    status: str = "running"
    ports: dict[str, str] = field(default_factory=dict)


class DockerConnector:
    """Abstract Docker connector. Real implementation would use docker-py."""

    NAME = "docker"
    ACTIONS = ["list_images", "list_containers", "container_logs", "start", "stop", "remove"]

    def execute(self, request: ToolRequest) -> Any:
        action = request.action
        params = request.parameters

        if action == "list_images":
            return {"images": []}
        elif action == "list_containers":
            return {"containers": []}
        elif action == "container_logs":
            return {"logs": "", "container_id": params.get("container_id", "")}
        elif action == "start":
            return {"container_id": params.get("container_id", ""), "action": "started"}
        elif action == "stop":
            return {"container_id": params.get("container_id", ""), "action": "stopped"}
        elif action == "remove":
            return {"container_id": params.get("container_id", ""), "action": "removed"}
        return {"error": f"Unknown action: {action}"}
