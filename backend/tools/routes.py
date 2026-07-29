"""REST API routes for MCP & External Tools Platform (HOS-049)."""

from __future__ import annotations

from typing import Any, Optional

from .mcp import MCPCall, MCPClient, MCPRegistry, MCPServer, MCPStatus, MCPTool, MCPTransport
from .tool_executor import ToolExecutor
from .tool_health import ToolHealth
from .tool_memory import ToolMemory
from .tool_models import (
    ExecutionStatus,
    ToolCategory,
    ToolDefinition,
    ToolPermission,
    ToolRequest,
    ToolStatus,
    ToolType,
)
from .tool_policy import ToolPolicy
from .tool_registry import ToolRegistry
from .tool_router import ToolRouter
from .tool_sandbox import ToolSandbox

# ── Global instances ─────────────────────────────────────────

_registry = ToolRegistry()
_policy = ToolPolicy()
_sandbox = ToolSandbox()
_executor = ToolExecutor(_policy, _sandbox)
_router = ToolRouter(_registry)
_health = ToolHealth()
_memory = ToolMemory()

_mcp_registry = MCPRegistry()
_mcp_client = MCPClient(_mcp_registry)


# ── Tool endpoints ───────────────────────────────────────────

def handle_get_tools(
    tool_type: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
) -> dict:
    """GET /tools"""
    tools = _registry.list_all()
    if tool_type:
        try:
            tools = _registry.list_by_type(ToolType(tool_type))
        except ValueError:
            pass
    elif category:
        try:
            tools = _registry.list_by_category(ToolCategory(category))
        except ValueError:
            pass
    elif status:
        try:
            tools = _registry.list_by_status(ToolStatus(status))
        except ValueError:
            pass
    elif tag:
        tools = _registry.list_by_tag(tag)

    return {"tools": [_tool_to_dict(t) for t in tools], "count": len(tools), "stats": _registry.stats()}


def handle_get_tool(tool_id: str) -> Optional[dict]:
    """GET /tools/{id}"""
    tool = _registry.get(tool_id)
    if tool is None:
        return None
    instance = _health.get(tool_id)
    mem_stats = _memory.get_tool_stats(tool_id)
    return {
        "tool": _tool_to_dict(tool),
        "instance": _instance_to_dict(instance) if instance else None,
        "memory": mem_stats,
    }


def handle_post_register(tool: dict) -> dict:
    """POST /tools/register"""
    t = ToolDefinition(
        name=tool.get("name", ""),
        tool_type=ToolType(tool.get("tool_type", "custom")),
        category=ToolCategory(tool.get("category", "system")),
        description=tool.get("description", ""),
        permissions=[ToolPermission(p) for p in tool.get("permissions", ["read"])],
        tags=tool.get("tags", []),
        timeout_seconds=tool.get("timeout_seconds", 30.0),
    )
    _registry.register(t)
    _health.register(t)
    return {"tool": _tool_to_dict(t), "registered": True}


def handle_post_execute(tool_id: str, action: str, parameters: dict,
                        agent_id: str = "", mission_id: str = "",
                        permission: str = "read") -> dict:
    """POST /tools/execute"""
    tool = _registry.get(tool_id)
    if tool is None:
        return {"error": f"Tool '{tool_id}' not found", "executed": False}

    request = ToolRequest(
        tool_id=tool_id, action=action, parameters=parameters,
        agent_id=agent_id, mission_id=mission_id,
        permission_level=ToolPermission(permission),
        timeout_seconds=tool.timeout_seconds,
    )
    result = _executor.execute(request, tool)

    # Record health + memory
    _health.record_execution(tool_id, result.status == ExecutionStatus.COMPLETED, result.duration_ms)
    _memory.record(request, result, tool)

    return {"executed": result.status == ExecutionStatus.COMPLETED,
            "status": result.status.value, "result": result.data,
            "error": result.error, "duration_ms": result.duration_ms}


def handle_post_select(action: str = "", context: Optional[dict] = None,
                       permission: str = "read",
                       preferred_type: Optional[str] = None) -> dict:
    """POST /tools/select"""
    pref = ToolType(preferred_type) if preferred_type else None
    tool, justification, confidence = _router.select(
        action=action, context=context,
        permission=ToolPermission(permission),
        preferred_type=pref,
    )
    return {
        "tool": _tool_to_dict(tool) if tool else None,
        "justification": justification,
        "confidence": confidence,
        "selected": tool is not None,
    }


def handle_get_health() -> dict:
    """GET /tools/health"""
    return _health.stats()


def handle_get_metrics() -> dict:
    """GET /tools/metrics"""
    return {
        "registry": _registry.stats(),
        "executor": _executor.stats(),
        "health": _health.stats(),
        "memory": _memory.stats(),
        "router": _router.stats(),
    }


# ── MCP endpoints ────────────────────────────────────────────

def handle_get_mcp_servers() -> dict:
    """GET /mcp/servers"""
    servers = _mcp_registry.list_servers()
    return {"servers": [_mcp_server_to_dict(s) for s in servers], "count": len(servers)}


def handle_post_mcp_connect(name: str, host: str = "localhost", port: int = 0,
                            transport: str = "http") -> dict:
    """POST /mcp/connect"""
    server = MCPServer(name=name, host=host, port=port,
                       transport=MCPTransport(transport))
    _mcp_registry.register_server(server)
    success = _mcp_client.connect(server)
    return {"server": _mcp_server_to_dict(server), "connected": success}


def handle_post_mcp_disconnect(server_id: str) -> dict:
    """POST /mcp/disconnect"""
    success = _mcp_client.disconnect(server_id)
    return {"server_id": server_id, "disconnected": success}


# ── Serialization helpers ────────────────────────────────────

def _tool_to_dict(t: ToolDefinition) -> dict:
    return {
        "id": t.id, "name": t.name, "tool_type": t.tool_type.value,
        "category": t.category.value, "version": t.version,
        "description": t.description,
        "permissions": [p.value for p in t.permissions],
        "dependencies": t.dependencies, "tags": t.tags,
        "resource_cost_mb": t.resource_cost_mb,
        "timeout_seconds": t.timeout_seconds,
        "max_retries": t.max_retries, "status": t.status.value,
        "sandbox_required": t.sandbox_required,
        "policy_required": t.policy_required,
    }


def _instance_to_dict(i: ToolInstance) -> dict:
    return {
        "id": i.id, "tool_id": i.tool_id, "health": i.health.value,
        "latency_ms": i.latency_ms, "error_count": i.error_count,
        "total_executions": i.total_executions,
    }


def _mcp_server_to_dict(s: MCPServer) -> dict:
    return {
        "id": s.id, "name": s.name, "transport": s.transport.value,
        "host": s.host, "port": s.port, "version": s.version,
        "capabilities": s.capabilities, "status": s.status.value,
        "error": s.error,
    }
