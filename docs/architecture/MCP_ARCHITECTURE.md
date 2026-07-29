# MCP Architecture (HOS-049)

## Overview

MCP (Model Context Protocol) integration within Hermes OS. Multiple MCP servers can be registered, connected, and their tools called through a unified client.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  MCPClient                        │
│        (connect, disconnect, ping, call)          │
├──────────────────────────────────────────────────┤
│                MCPRegistry                        │
│     (servers registry + tools per server)         │
├──────────────┬──────────────┬────────────────────┤
│  MCPServer   │   MCPTool    │     MCPCall        │
│  (metadata)  │  (schema)    │   (invocation)     │
└──────────────┴──────────────┴────────────────────┘
```

## Components

### MCPRegistry (`mcp_registry.py`)
- Thread-safe server registry
- Tools per server tracking
- Status-based counting

### MCPClient (`mcp_client.py`)
- Connect/disconnect lifecycle
- Tool listing per server
- Tool calling with result capture
- Ping health check
- Call history

### MCPServer
```python
@dataclass
class MCPServer:
    id: str
    name: str
    transport: MCPTransport  # stdio, http, sse
    host: str
    port: int
    version: str
    capabilities: list[str]
    status: MCPStatus       # DISCONNECTED, CONNECTING, CONNECTED, ERROR
```

### MCPTool
```python
@dataclass
class MCPTool:
    id: str
    server_id: str
    name: str
    description: str
    input_schema: dict     # JSON Schema for arguments
```

### MCPCall
```python
@dataclass
class MCPCall:
    id: str
    tool_id: str
    server_id: str
    arguments: dict
    result: Any
    error: str
    success: bool
    duration_ms: float
```

## Transports

| Transport | Description |
|---|---|
| `stdio` | Standard I/O subprocess (local) |
| `http` | HTTP REST API (remote) |
| `sse` | Server-Sent Events (streaming) |

## Lifecycle

```
1. MCPServer → MCPRegistry.register_server()
2. MCPClient.connect() → MCPStatus.CONNECTED
3. MCPClient.list_tools() → [MCPTool, ...]
4. MCPClient.call(tool, server, args) → MCPCall
5. MCPClient.disconnect() → MCPStatus.DISCONNECTED
```

## Future Extensibility

The current implementation uses a simulated transport layer. Real MCP integration would:
1. Implement stdio transport with subprocess management
2. Add HTTP/SSE transport with async HTTP client
3. Parse MCP protocol messages (JSON-RPC 2.0)
4. Handle server capabilities negotiation
5. Support tool input_schema validation
