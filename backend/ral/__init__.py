"""Runtime Abstraction Layer (RAL) — public namespace.

This module exposes the strict public surface of the RAL as defined by
HOS-001. It re-exports runtime contracts, capabilities, the model
router contract, and the event bus contract. Concrete implementations
are kept in sub-modules and are intentionally not imported here.
"""

from backend.ral.runtime import CapabilitySet, RuntimeInterface, RuntimeStatus
from backend.ral.capabilities import (
    BrowserAction,
    BrowserCapability,
    BrowserPage,
    BrowserResult,
    CapabilityInterface,
    ChatCapability,
    ChatResponse,
    ChatStreamCapability,
    DelegateCapability,
    DelegationResult,
    FilesCapability,
    MemoryCapability,
    SandboxSpec,
    SkillDescriptor,
    SkillResult,
    SkillsCapability,
    TerminalCapability,
    TerminalResult,
    ToolResult,
    ToolsCapability,
    VisionCapability,
    VisionResult,
)
from backend.ral.model_router import (
    DecisionPath,
    DecisionStep,
    ModelDecision,
    ModelRouterInterface,
    RoutingContext,
    TaskRequest,
)
from backend.ral.event_bus import (
    Event,
    EventBusInterface,
    EventId,
    SubscriptionId,
    Topic,
    TopicPattern,
)
from backend.ral.runtime_config import RuntimeConfig
from backend.ral.runtime_registry import RuntimeRegistry
from backend.ral.runtime_factory import RuntimeFactory, RuntimeLifecycle
from backend.ral.runtime_context import ActiveRuntimeContext
from backend.ral.runtime_selector import RuntimeSelector, RuntimeSelectionError
from backend.ral.runtime_router import RuntimeRouter, RuntimeExecutionError
from backend.ral.runtime_health import (
    RuntimeHealthError,
    RuntimeHealthMonitor,
    RuntimeHealthStatus,
    RuntimeMetrics,
)

__all__ = [
    # runtime
    "CapabilitySet",
    "RuntimeInterface",
    "RuntimeStatus",
    # capabilities
    "CapabilityInterface",
    "ChatCapability",
    "ChatResponse",
    "ChatStreamCapability",
    "ToolsCapability",
    "ToolResult",
    "DelegateCapability",
    "DelegationResult",
    "MemoryCapability",
    "BrowserCapability",
    "BrowserAction",
    "BrowserPage",
    "BrowserResult",
    "TerminalCapability",
    "SandboxSpec",
    "TerminalResult",
    "FilesCapability",
    "VisionCapability",
    "VisionResult",
    "SkillsCapability",
    "SkillDescriptor",
    "SkillResult",
    # model router
    "ModelRouterInterface",
    "TaskRequest",
    "RoutingContext",
    "ModelDecision",
    "DecisionStep",
    "DecisionPath",
    # event bus
    "EventBusInterface",
    "Topic",
    "TopicPattern",
    "Event",
    "EventId",
    "SubscriptionId",
    # runtime config — HOS-005
    "RuntimeConfig",
    # runtime registry & factory — HOS-007
    "RuntimeRegistry",
    "RuntimeFactory",
    "RuntimeLifecycle",
    # runtime context & selector — HOS-009
    "ActiveRuntimeContext",
    "RuntimeSelector",
    "RuntimeSelectionError",
    # runtime router — HOS-010
    "RuntimeRouter",
    "RuntimeExecutionError",
    # runtime health — HOS-011
    "RuntimeHealthMonitor",
    "RuntimeHealthStatus",
    "RuntimeMetrics",
    "RuntimeHealthError",
]
