"""Tests for derive_mcp_status (R-006 Phase 5).

Five explicit states so the Cockpit never shows "MCP connected" just
because a class exists.
"""
from __future__ import annotations

from backend.tools.mcp.mcp_models import MCPServer, MCPStatus
from backend.tools.mcp.mcp_status import derive_mcp_status


class TestDeriveMcpStatus:
    def test_not_installed_is_not_configured(self):
        assert derive_mcp_status(installed=False, version=None, server=None) == "not_configured"

    def test_installed_but_no_version_is_unavailable(self):
        """Installed=True from a loose presence check (npx/bunx exists) but
        every real health probe has failed — exactly Oh My Pi's observed
        state (npm package doesn't resolve to a runnable executable)."""
        assert derive_mcp_status(installed=True, version=None, server=None) == "unavailable"

    def test_installed_and_working_but_not_bound_is_unbound(self):
        assert derive_mcp_status(installed=True, version="2.4.4", server=None) == "unbound"

    def test_bound_server_reporting_connected(self):
        server = MCPServer(status=MCPStatus.CONNECTED)
        assert derive_mcp_status(installed=True, version="2.4.4", server=server) == "connected"

    def test_bound_server_reporting_disconnected(self):
        server = MCPServer(status=MCPStatus.DISCONNECTED)
        assert derive_mcp_status(installed=True, version="2.4.4", server=server) == "disconnected"

    def test_bound_server_with_no_status_attribute_defaults_disconnected(self):
        """A caller could plausibly bind something that isn't a real
        MCPServer (e.g. in a test double) — must not crash, must not claim
        connected without evidence."""
        assert derive_mcp_status(installed=True, version="1.0", server=object()) == "disconnected"
