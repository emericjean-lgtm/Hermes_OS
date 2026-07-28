"""Hermes Agent Integration (HOS-023).

This package provides an :class:`HermesAgentAdapter` that bridges the
Hermes OS abstractions (RAL, Agent, Memory, Skills) with the existing
Hermes Agent codebase.

The adapter encapsulates every direct dependency on Hermes Agent so
that the rest of the system interacts only through the adapter's
public API — keeping the architecture decoupled and testable.

Mapping Hermes OS → Hermes Agent:

    Hermes OS abstraction        →  Hermes Agent concrete
    ────────────────────────────    ─────────────────────
    RuntimeInterface / ChatCap.      BaseAgent / OllamaClient
    RuntimeDecision                  ModelRouter
    UnifiedMemory                   EchoAgent (memory + skills)
    AdaptiveSkillOrchestrator       EchoAgent (skill library)
    ExecutionGraph / TaskPlan       HermesAgentTask / Subagents
"""

from backend.integrations.hermes_agent.adapter import (
    HermesAgentAdapter,
    HermesAgentCapabilities,
    HermesAgentConfiguration,
    HermesAgentError,
    HermesAgentExecution,
    HermesAgentSession,
    HermesAgentStatus,
    HermesAgentTask,
    HermesCapability,
)

__all__ = [
    "HermesAgentAdapter",
    "HermesAgentCapabilities",
    "HermesAgentConfiguration",
    "HermesAgentError",
    "HermesAgentExecution",
    "HermesAgentSession",
    "HermesAgentStatus",
    "HermesAgentTask",
    "HermesCapability",
]
