"""MCP client — Model Context Protocol integration (HOS-049)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from .mcp_models import MCPCall, MCPServer, MCPStatus, MCPTool
from .mcp_registry import MCPRegistry


class MCPClient:
    """Client for connecting to MCP servers, discovering tools, and calling them."""

    def __init__(self, registry: MCPRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._history: list[MCPCall] = []

    def connect(self, server: MCPServer) -> bool:
        with self._lock:
            server.status = MCPStatus.CONNECTING
            try:
                # Simulated connection — real implementation would use
                # stdio subprocess or HTTP/SSE transport
                server.status = MCPStatus.CONNECTED
                server.connected_at = datetime.now(timezone.utc)
                server.error = ""
                return True
            except Exception as e:
                server.status = MCPStatus.ERROR
                server.error = str(e)
                return False

    def disconnect(self, server_id: str) -> bool:
        server = self._registry.get(server_id)
        if server is None:
            return False
        with self._lock:
            server.status = MCPStatus.DISCONNECTED
            return True

    def list_tools(self, server: MCPServer) -> list[MCPTool]:
        return self._registry.list_tools(server.id)

    def call(self, tool: MCPTool, server: MCPServer, arguments: dict[str, Any]) -> MCPCall:
        call = MCPCall(tool_id=tool.id, server_id=server.id, arguments=arguments)

        if server.status != MCPStatus.CONNECTED:
            call.error = f"Server '{server.name}' is not connected"
            return call

        start = time.monotonic()
        try:
            # Simulated tool call — real impl would use transport
            call.result = {"status": "ok", "tool": tool.name, "args": arguments}
            call.success = True
        except Exception as e:
            call.error = str(e)
            call.success = False

        call.duration_ms = (time.monotonic() - start) * 1000

        with self._lock:
            self._history.append(call)
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

        return call

    def get_history(self, limit: int = 50) -> list[MCPCall]:
        with self._lock:
            return list(self._history[-limit:])

    def ping(self, server: MCPServer) -> bool:
        with self._lock:
            server.last_ping = datetime.now(timezone.utc)
            return server.status == MCPStatus.CONNECTED

    def stats(self) -> dict:
        with self._lock:
            return {
                "connected_servers": self._registry.count_by_status(MCPStatus.CONNECTED),
                "total_servers": self._registry.count(),
                "total_tools": self._registry.count_tools(),
                "total_calls": len(self._history),
            }
