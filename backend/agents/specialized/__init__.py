"""Specialized Hermes agents (HOS-054C+).

This package contains domain-specific agent implementations that
extend the core Hermes multi-agent system with specialized capabilities.

Current agents:
- KlaatCodeAgent: coding agent using KlaatCode MCP tools
"""

from .klaatcode import KlaatCodeAgent, KlaatCodeProfile, create_klaatcode_agent

__all__ = [
    "KlaatCodeAgent",
    "KlaatCodeProfile",
    "create_klaatcode_agent",
]
