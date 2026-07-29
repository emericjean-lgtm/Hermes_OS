"""KlaatCode Agent — specialized coding agent for Hermes OS (HOS-054C).

Provides:
- KlaatCodeAgent: full lifecycle coding agent using KlaatCode MCP tools
- KlaatCodeProfile: static profile with capabilities, skills, constraints
- KlaatCodeCapabilities: task types and mapping utilities
- Factory: create_klaatcode_agent() for easy instantiation

Integration points:
- AgentSupervisor HOS-043: registration, lifecycle, dispatch
- MCP Tools HOS-054B: analyze_project, inspect_code, generate_code_plan, etc.
- Execution Engine HOS-050: task scheduling, agent coordination
- EventBus HOS-034: klaatcode.agent.* and klaatcode.task.* events
- Memory HOS-047: episodic recording, experience learning
"""

from .klaatcode_agent import (
    KlaatCodeAgent,
    KlaatCodeTaskRecord,
    KLATCODE_EVENTS,
    create_klaatcode_agent,
)
from .klaatcode_capabilities import (
    KlaatCodeAgentStatus,
    KlaatCodeTaskType,
    TASK_TO_CAPABILITY,
    TASK_TO_MCP_ACTION,
)
from .klaatcode_profile import KlaatCodeProfile

__all__ = [
    # Core
    "KlaatCodeAgent",
    "KlaatCodeProfile",
    "KlaatCodeTaskRecord",
    "KLATCODE_EVENTS",
    "create_klaatcode_agent",
    # Capabilities
    "KlaatCodeAgentStatus",
    "KlaatCodeTaskType",
    "TASK_TO_CAPABILITY",
    "TASK_TO_MCP_ACTION",
]
