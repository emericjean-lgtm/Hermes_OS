"""Integration-test fixtures."""

import pytest


# ── R-002 P5: an agent with no adapter must not report success ────────

@pytest.fixture(autouse=True)
def _bind_stub_mcp_adapters(monkeypatch):
    """See :mod:`tests.support.stub_agents`.

    The full-system tests drive the specialised agents without binding an MCP
    adapter and assert the task completes. That used to hold only because the
    agents reported success for work they had not done (R-002 P5).
    """
    from tests.support import stub_agents

    stub_agents.install(monkeypatch)
