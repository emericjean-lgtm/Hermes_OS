"""MCP registry — tracks MCP servers and their tools (HOS-049)."""

from __future__ import annotations

import threading
from typing import Optional

from .mcp_models import MCPServer, MCPStatus, MCPTool


class MCPRegistry:
    """Thread-safe registry of MCP servers and their registered tools."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._servers: dict[str, MCPServer] = {}
        self._tools: dict[str, list[MCPTool]] = {}  # server_id → tools

    def register_server(self, server: MCPServer) -> MCPServer:
        with self._lock:
            self._servers[server.id] = server
            self._tools.setdefault(server.id, [])
            return server

    def get(self, server_id: str) -> Optional[MCPServer]:
        with self._lock:
            return self._servers.get(server_id)

    def list_servers(self) -> list[MCPServer]:
        with self._lock:
            return list(self._servers.values())

    def remove(self, server_id: str) -> bool:
        with self._lock:
            self._tools.pop(server_id, None)
            return self._servers.pop(server_id, None) is not None

    def register_tool(self, tool: MCPTool) -> MCPTool:
        with self._lock:
            self._tools.setdefault(tool.server_id, []).append(tool)
            return tool

    def list_tools(self, server_id: str) -> list[MCPTool]:
        with self._lock:
            return list(self._tools.get(server_id, []))

    def get_tool(self, tool_id: str) -> Optional[MCPTool]:
        with self._lock:
            for tools in self._tools.values():
                for t in tools:
                    if t.id == tool_id:
                        return t
            return None

    def count(self) -> int:
        with self._lock:
            return len(self._servers)

    def count_tools(self) -> int:
        with self._lock:
            return sum(len(tools) for tools in self._tools.values())

    def count_by_status(self, status: MCPStatus) -> int:
        with self._lock:
            return sum(1 for s in self._servers.values() if s.status == status)
