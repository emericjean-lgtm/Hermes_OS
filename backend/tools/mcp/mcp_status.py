"""Real MCP binding/connection status for a provider adapter (R-006 Phase 5).

Five explicit states, never "connected" just because a class exists:

- ``not_configured`` — the underlying CLI/tool isn't installed at all.
- ``unavailable`` — installed (per a loose presence check), but no real
  successful call has ever landed — a genuine version/health probe keeps
  failing. This is what "Installed: yes" was hiding: a provider can report
  installed while every real invocation errors out.
- ``unbound`` — installed and has answered at least once, but the adapter
  was never bound to a real ``MCPServer`` registry entry.
- ``connected`` / ``disconnected`` — bound to a real ``MCPServer`` entry;
  reflects that entry's own ``MCPStatus`` honestly. No adapter in this
  codebase performs a live MCP protocol handshake (KlaatCode/Oh My Pi are
  local CLI wrappers, not network MCP clients), so this reads
  ``disconnected`` unless something genuinely sets the registry entry's
  status to connected — reporting ``connected`` without ever checking
  would be exactly the fabrication this function exists to avoid.
"""
from __future__ import annotations

from typing import Any, Optional


def derive_mcp_status(
    *, installed: bool, version: Optional[str], server: Any,
) -> str:
    if not installed:
        return "not_configured"
    if not version:
        return "unavailable"
    if server is None:
        return "unbound"
    status = getattr(server, "status", None)
    value = getattr(status, "value", status)
    return "connected" if value == "connected" else "disconnected"
