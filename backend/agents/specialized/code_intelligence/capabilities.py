"""Code Intelligence Agent capabilities (HOS-055D).

Defines capabilities and task type mappings for the meta-agent that
routes code tasks between KlaatCode and Oh My Pi.
"""

from enum import Enum


class CodeIntelligenceAgentStatus(str, Enum):
    """CodeIntelligenceAgent operational status."""
    IDLE = "idle"
    ROUTING = "routing"
    EXECUTING_KLATCODE = "executing_klaatcode"
    EXECUTING_OHMYPI = "executing_ohmypi"
    EXECUTING_HERMES_NATIVE = "executing_hermes_native"
    EXECUTING_HYBRID = "executing_hybrid"
    VALIDATING = "validating"
    RECORDING = "recording"


class CICapability(str, Enum):
    """Code Intelligence Agent capabilities."""
    CODE_ANALYSIS = "code_analysis"
    REFACTORING = "refactoring"
    DEBUGGING = "debugging"
    ARCHITECTURE_REVIEW = "architecture_review"
    CODE_GENERATION = "code_generation"
    TEST_GENERATION = "test_generation"
    OPTIMIZATION = "optimization"


# Task → Agent capability mapping
TASK_TO_CI_CAPABILITY = {
    "code_analysis": CICapability.CODE_ANALYSIS,
    "refactoring": CICapability.REFACTORING,
    "debugging": CICapability.DEBUGGING,
    "architecture_review": CICapability.ARCHITECTURE_REVIEW,
    "code_generation": CICapability.CODE_GENERATION,
    "test_generation": CICapability.TEST_GENERATION,
    "optimization": CICapability.OPTIMIZATION,
    "diagnostics": CICapability.CODE_ANALYSIS,
    "code_review": CICapability.CODE_ANALYSIS,
    "documentation": CICapability.CODE_GENERATION,
}


# Event types published by the CodeIntelligenceAgent
CI_EVENTS = {
    "agent_ready": "ci.agent.ready",
    "routing_decided": "ci.routing.decided",
    "task_started": "ci.task.started",
    "task_completed": "ci.task.completed",
    "task_failed": "ci.task.failed",
    "hybrid_executed": "ci.hybrid.executed",
    "recorded_to_memory": "ci.memory.recorded",
    # HermesNativeExecutor (R-006 Phase 3) — its own execution outcome,
    # distinct from task_completed/task_failed which cover every provider.
    "hermes_native_completed": "ci.hermes_native.completed",
    "hermes_native_failed": "ci.hermes_native.failed",
}
