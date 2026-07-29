"""MCP models — Model Context Protocol data structures (HOS-049)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MCPStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MCPTransport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


@dataclass
class MCPServer:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    transport: MCPTransport = MCPTransport.HTTP
    host: str = "localhost"
    port: int = 0
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)
    status: MCPStatus = MCPStatus.DISCONNECTED
    connected_at: datetime = None
    last_ping: datetime | None = None
    error: str = ""


@dataclass
class MCPTool:
    id: str = field(default_factory=lambda: str(uuid4()))
    server_id: str = ""
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MCPCall:
    id: str = field(default_factory=lambda: str(uuid4()))
    tool_id: str = ""
    server_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    success: bool = False
    duration_ms: float = 0.0
    called_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
