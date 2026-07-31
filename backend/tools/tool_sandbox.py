"""Tool sandbox — isolates tool execution in controlled environments (HOS-049)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SandboxConfig:
    """Configuration for a tool sandbox."""
    workspace_id: str = ""
    read_only: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=lambda: [".env", "/etc", "/proc"])
    network_allowed: bool = False
    allowed_hosts: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    max_memory_mb: float = 256.0
    max_disk_mb: float = 1024.0
    max_duration_seconds: float = 60.0


class ToolSandbox:
    """Manages isolated execution environments for tools.

    Integrates with Workspace Manager (HOS-045) for per-agent workspaces.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._configs: dict[str, SandboxConfig] = {}  # tool_id → config
        self._default_config = SandboxConfig()

    def configure(self, tool_id: str, config: SandboxConfig) -> None:
        with self._lock:
            self._configs[tool_id] = config

    def get_config(self, tool_id: str) -> SandboxConfig:
        with self._lock:
            return self._configs.get(tool_id, self._default_config)

    def validate_path(self, tool_id: str, path: str) -> bool:
        """Check if a path is allowed for a given tool's sandbox."""
        config = self.get_config(tool_id)

        # Check denied paths first
        for denied in config.denied_paths:
            if path.startswith(denied):
                return False

        # If no allowed paths specified, allow all non-denied
        if not config.allowed_paths:
            return True

        # Check allowed paths
        for allowed in config.allowed_paths:
            if path.startswith(allowed):
                return True

        return False

    def validate_network(self, tool_id: str, host: str) -> bool:
        """Check if a network host is allowed."""
        config = self.get_config(tool_id)
        if not config.network_allowed:
            return False
        if not config.allowed_hosts:
            return True
        return host in config.allowed_hosts

    def create_for_agent(self, tool_id: str, agent_id: str, workspace_id: str) -> SandboxConfig:
        """Create a sandbox config tied to an agent's workspace."""
        with self._lock:
            config = SandboxConfig(workspace_id=workspace_id)
            self._configs[tool_id] = config
            return config

    def destroy(self, tool_id: str) -> bool:
        with self._lock:
            return self._configs.pop(tool_id, None) is not None

    def stats(self) -> dict:
        with self._lock:
            return {"active_sandboxes": len(self._configs)}
