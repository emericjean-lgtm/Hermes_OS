"""Agent Supervisor (HOS-043).

Supervises agent execution of mission tasks.
Orchestrates agent lifecycle, capability matching, and task dispatch.
"""

from backend.agents.agent_models import (
    Agent,
    AgentCapability,
    AgentProfile,
    AgentStatus,
    ExecutionContext,
    ExecutionResult,
    AgentMetrics,
    AgentTask,
)
from backend.agents.agent_registry import AgentRegistry
from backend.agents.capability_matcher import CapabilityMatcher
from backend.agents.execution_context import ExecutionContextManager
from backend.agents.agent_lifecycle import AgentLifecycle
from backend.agents.task_dispatcher import TaskDispatcher
from backend.agents.agent_supervisor import AgentSupervisor

__all__ = [
    "Agent",
    "AgentCapability",
    "AgentProfile",
    "AgentStatus",
    "ExecutionContext",
    "ExecutionResult",
    "AgentMetrics",
    "AgentTask",
    "AgentRegistry",
    "CapabilityMatcher",
    "ExecutionContextManager",
    "AgentLifecycle",
    "TaskDispatcher",
    "AgentSupervisor",
]
