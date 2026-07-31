"""MCP client — Model Context Protocol integration (HOS-049).

Real transport (R-001). ``connect()`` and ``call()` used to be:

    # Simulated connection — real implementation would use
    # stdio subprocess or HTTP/SSE transport
    server.status = MCPStatus.CONNECTED
    return True

so ``POST /api/v1/mcp/connect`` reported ``connected: true`` for any host,
including unreachable ones and link-local metadata addresses, without emitting a
packet — and every tool call returned a canned ``{"status": "ok"}``. The Tools
Center presented servers as connected that had never been contacted.

Both now perform real HTTP with a bounded timeout and bounded retries, and report
failure when the server cannot be reached. ``connected`` means connected.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .mcp_models import MCPCall, MCPServer, MCPStatus, MCPTool
from .mcp_registry import MCPRegistry

logger = logging.getLogger("hermes_os.mcp.client")

#: Bounded so a dead server cannot stall a request thread.
CONNECT_TIMEOUT_S = 5.0
CALL_TIMEOUT_S = 30.0
MAX_ATTEMPTS = 2


class MCPClient:
    """Client for connecting to MCP servers, discovering tools, and calling them."""

    def __init__(self, registry: MCPRegistry, *, opener: Any = None) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        self._history: list[MCPCall] = []
        # Injectable so tests exercise this code without a socket.
        self._opener = opener or urllib.request.urlopen

    # ── transport ───────────────────────────────────────────────────

    def _endpoint(self, server: MCPServer) -> str:
        port = f":{server.port}" if server.port else ""
        return f"http://{server.host}{port}"

    def _post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """One JSON-RPC POST. Raises on any transport or protocol failure."""
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        with self._opener(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        # An MCP server may answer JSON or an SSE frame; accept both.
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        raise ValueError(f"no JSON payload in response: {body[:120]!r}")

    def _attempt(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Retry a bounded number of times, then give up honestly."""
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._post(url, payload, timeout)
            except Exception as exc:
                last = exc
                if attempt < MAX_ATTEMPTS:
                    time.sleep(0.2 * attempt)
        assert last is not None
        raise last

    # ── lifecycle ───────────────────────────────────────────────────

    def connect(self, server: MCPServer) -> bool:
        """Perform a real MCP ``initialize`` handshake.

        Returns True only when the server answered. On failure the server is
        marked ERROR with the reason, and False is returned — never an optimistic
        success.
        """
        with self._lock:
            server.status = MCPStatus.CONNECTING
            url = f"{self._endpoint(server)}/mcp/"
            handshake = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "hermes-os", "version": "1.0.0"},
                },
            }
            try:
                reply = self._attempt(url, handshake, CONNECT_TIMEOUT_S)
            except Exception as exc:
                server.status = MCPStatus.ERROR
                server.error = f"{type(exc).__name__}: {exc}"
                server.connected_at = None
                logger.warning("MCP connect to %s failed: %s", url, server.error)
                return False

            if "error" in reply:
                server.status = MCPStatus.ERROR
                server.error = str(reply["error"])[:200]
                return False

            result = reply.get("result", {}) or {}
            info = result.get("serverInfo", {}) or {}
            server.version = str(info.get("version") or server.version)
            server.capabilities = sorted((result.get("capabilities") or {}).keys())
            server.status = MCPStatus.CONNECTED
            server.connected_at = datetime.now(timezone.utc)
            server.error = ""
            logger.info("MCP connected to %s (%s)", url, server.version)
            return True

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

        start = time.perf_counter()
        try:
            reply = self._attempt(
                f"{self._endpoint(server)}/mcp/",
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool.name, "arguments": arguments},
                },
                CALL_TIMEOUT_S,
            )
            if "error" in reply:
                call.error = str(reply["error"])[:300]
                call.success = False
            else:
                call.result = reply.get("result", {})
                call.success = True
        except Exception as e:
            # The call did not happen. Saying so is the whole point.
            call.error = f"{type(e).__name__}: {e}"
            call.success = False
            logger.warning("MCP call %s on %s failed: %s", tool.name, server.name, call.error)

        # perf_counter, not monotonic: monotonic resolves to 15.6ms on Windows,
        # which would quantise every sub-tick call to 0ms.
        call.duration_ms = (time.perf_counter() - start) * 1000

        with self._lock:
            self._history.append(call)
            if len(self._history) > 1000:
                self._history = self._history[-1000:]

        return call

    def get_history(self, limit: int = 50) -> list[MCPCall]:
        with self._lock:
            return list(self._history[-limit:])

    def ping(self, server: MCPServer) -> bool:
        """Probe the server for real rather than echoing the cached status.

        Returning `status == CONNECTED` made ping a no-op that could never
        detect a server that had gone away since connect().
        """
        with self._lock:
            server.last_ping = datetime.now(timezone.utc)
            if server.status != MCPStatus.CONNECTED:
                return False
            try:
                reply = self._post(
                    f"{self._endpoint(server)}/mcp/",
                    {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}},
                    CONNECT_TIMEOUT_S,
                )
            except Exception as exc:
                server.status = MCPStatus.ERROR
                server.error = f"ping failed: {type(exc).__name__}: {exc}"
                return False
            # A server that answers at all — even "method not found" — is alive.
            return isinstance(reply, dict)

    def stats(self) -> dict:
        with self._lock:
            return {
                "connected_servers": self._registry.count_by_status(MCPStatus.CONNECTED),
                "total_servers": self._registry.count(),
                "total_tools": self._registry.count_tools(),
                "total_calls": len(self._history),
            }
