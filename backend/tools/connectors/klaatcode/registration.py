"""KlaatCode registration module (HOS-054B).

Wires the KlaatCode MCP adapter into the Hermes Tool Platform:
    - Registers all 7 KlaatCode tools in the Tool Registry (HOS-049)
    - Registers KlaatCode as an MCP server in the MCP Registry (HOS-049)
    - Binds the adapter to the created MCP server

Usage (call once at startup):
    from backend.tools.connectors.klaatcode.registration import register_klaatcode
    register_klaatcode()
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.tools.mcp.mcp_models import (
    MCPServer,
    MCPTransport,
)
from backend.tools.tool_models import (
    ToolDefinition,
)

logger = logging.getLogger("hermes_os.klaatcode.registration")

# Store global references for later access
_registered_tool_defs: list[ToolDefinition] = []
_mcp_server: Optional[MCPServer] = None


def register_klaatcode(
    tool_registry=None,
    mcp_registry=None,
    adapter=None,
) -> dict:
    """Register KlaatCode in both the Tool and MCP registries.

    Args:
        tool_registry: Optional ToolRegistry instance from HOS-049.
        mcp_registry: Optional MCPRegistry instance from HOS-049.
        adapter: Optional KlaatCodeMCPAdapter instance.

    Returns:
        Status dict with counts of registered items.
    """
    # Import adapter lazily to avoid circular imports at module level
    from .klaatcode_client import KlaatCodeClient
    from .klaatcode_mcp_adapter import KlaatCodeMCPAdapter
    from backend.tools.tool_policy import ToolPolicy
    from backend.tools.tool_sandbox import ToolSandbox

    if adapter is None:
        client = KlaatCodeClient()
        policy = ToolPolicy()
        sandbox = ToolSandbox()
        adapter = KlaatCodeMCPAdapter(client, policy, sandbox)

    registered_tools = 0
    registered_mcp_tools = 0

    # ── 1. Register in Tool Registry (HOS-049) ──────────────
    if tool_registry is not None:
        td_map = adapter.get_tool_definitions()
        for action_name, td in td_map.items():
            try:
                tool_registry.register(td)
                _registered_tool_defs.append(td)
                registered_tools += 1
            except Exception as e:
                logger.warning("Failed to register KlaatCode tool '%s': %s", action_name, e)

    # ── 2. Register in MCP Registry (HOS-049) ───────────────
    if mcp_registry is not None:
        server = MCPServer(
            name="klaatcode",
            host="localhost",
            port=0,  # Local process, not network
            transport=MCPTransport.STDIO,
            version="0.1.0",
            capabilities=["code_analysis", "code_generation", "diagnostics"],
        )
        _mcp_server_obj = mcp_registry.register_server(server)

        # Bind the adapter to this server
        adapter.bind_server(_mcp_server_obj)

        # Register all MCP tools
        mt_map = adapter.get_mcp_tools()
        for action_name, mt in mt_map.items():
            try:
                mt.server_id = server.id
                mcp_registry.register_tool(mt)
                registered_mcp_tools += 1
            except Exception as e:
                logger.warning("Failed to register KlaatCode MCP tool '%s': %s", action_name, e)

        global _mcp_server
        _mcp_server = _mcp_server_obj

    # ── 3. Log summary ──────────────────────────────────────
    status = adapter.get_status()
    logger.info(
        "KlaatCode registered: %d tools in Tool Registry, %d tools in MCP Registry, installed=%s, version=%s",
        registered_tools,
        registered_mcp_tools,
        status.get("installed", False),
        status.get("version", "unknown"),
    )

    return {
        "registered_tools": registered_tools,
        "registered_mcp_tools": registered_mcp_tools,
        "installed": status.get("installed", False),
        "version": status.get("version", None),
        "capabilities": len(adapter.get_capabilities()),
    }


def get_registered_mcp_server() -> Optional[MCPServer]:
    """Return the MCP server created for KlaatCode (if registered)."""
    return _mcp_server


def get_registered_tools() -> list[ToolDefinition]:
    """Return the ToolDefinition entries registered for KlaatCode."""
    return list(_registered_tool_defs)
