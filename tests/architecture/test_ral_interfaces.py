"""HOS-001 sentinelle — Runtime Abstraction Layer interfaces.

These tests verify that the contracts introduced by HOS-001 are
importable, correctly typed as ``typing.Protocol``, runtime-checkable,
and expose the expected topic vocabulary.
"""
from __future__ import annotations

import typing
from dataclasses import is_dataclass


from backend.ral import (
    BrowserCapability,
    CapabilityInterface,
    ChatCapability,
    DecisionPath,
    DelegateCapability,
    Event,
    EventBusInterface,
    EventId,
    FilesCapability,
    MemoryCapability,
    ModelDecision,
    ModelRouterInterface,
    RuntimeInterface,
    RuntimeStatus,
    SandboxSpec,
    SkillResult,
    SkillsCapability,
    SubscriptionId,
    TaskRequest,
    TerminalCapability,
    TerminalResult,
    ToolResult,
    ToolsCapability,
    Topic,
    TopicPattern,
    VisionCapability,
)


def _is_runtime_checkable(protocol: type) -> bool:
    """Return True if the given class is a runtime-checkable Protocol.

    Python 3.10 stores the flag as ``_is_runtime_protocol`` while later
    versions also expose ``_is_runtime_checkable``. We accept either.
    """
    is_flag_set = getattr(protocol, "_is_runtime_checkable", False) or getattr(
        protocol, "_is_runtime_protocol", False
    )
    return issubclass(protocol, typing.Protocol) and bool(is_flag_set)


def test_ral_protocols_are_runtime_checkable() -> None:
    """All public RAL protocols must be runtime-checkable."""
    protocols = [
        RuntimeInterface,
        EventBusInterface,
        ModelRouterInterface,
        CapabilityInterface,
        ChatCapability,
        ToolsCapability,
        DelegateCapability,
        MemoryCapability,
        BrowserCapability,
        TerminalCapability,
        FilesCapability,
        VisionCapability,
        SkillsCapability,
    ]
    for proto in protocols:
        assert _is_runtime_checkable(proto), f"{proto.__name__} must be @runtime_checkable"


def test_topic_enum_matches_hos_001_specification() -> None:
    """Topic must contain exactly the 28 topics defined by HOS-001 + D-20."""
    expected_topics = {
        "runtime.started",
        "runtime.stopped",
        "runtime.health",
        "capability.registered",
        "capability.unregistered",
        "task.created",
        "task.started",
        "task.completed",
        "task.failed",
        "task.cancelled",
        "memory.updated",
        "memory.deleted",
        "knowledge.indexed",
        "skill.generated",
        "skill.compilation.completed",
        "workflow.started",
        "workflow.completed",
        "workflow.failed",
        "evolution.triggered",
        "evolution.completed",
        "delegation.requested",
        "delegation.completed",
        "security.validation.requested",
        "security.validation.granted",
        "security.validation.denied",
        "system.metrics",
        "sdsl.message",
        "agent.message",
    }
    actual_topics = {t.value for t in Topic}
    missing = expected_topics - actual_topics
    extra = actual_topics - expected_topics

    assert not missing, f"missing topics: {missing}"
    assert not extra, f"unexpected extra topics: {extra}"
    assert len(Topic) == 28, "expected exactly 28 topics"


def test_topic_values_are_strings() -> None:
    """Topic members must be strings (HOS-001 convention)."""
    for topic in Topic:
        assert isinstance(topic.value, str)


def test_topic_pattern_is_frozen_dataclass() -> None:
    """TopicPattern must be an immutable dataclass with a 'pattern' field."""
    assert is_dataclass(TopicPattern)
    assert TopicPattern.__dataclass_params__.frozen
    assert hasattr(TopicPattern("test.*"), "pattern")


def test_event_is_frozen_dataclass() -> None:
    """Event must be an immutable dataclass."""
    assert is_dataclass(Event)
    assert Event.__dataclass_params__.frozen


def test_shared_dataclasses_are_frozen() -> None:
    """Value objects returned by capabilities must be immutable."""
    frozen = [
        TaskRequest,
        TerminalResult,
        ToolResult,
        SkillResult,
        SandboxSpec,
        ModelDecision,
        DecisionPath,
    ]
    for cls in frozen:
        assert is_dataclass(cls), f"{cls.__name__} must be a dataclass"
        assert cls.__dataclass_params__.frozen, f"{cls.__name__} must be frozen"


def test_event_id_and_subscription_id_are_strings() -> None:
    """EventId and SubscriptionId must alias ``str`` for type safety."""
    assert EventId is str
    assert SubscriptionId is str


def test_runtime_status_is_string_enum() -> None:
    """RuntimeStatus must be a string-backed enum."""
    for status in RuntimeStatus:
        assert isinstance(status.value, str)


def test_no_runtime_concrete_import() -> None:
    """backend.ral must not leak any concrete runtime implementation."""
    import backend.ral  # noqa: F401

    module = typing.cast(object, backend.ral)
    names = dir(module)
    forbidden = {"HermesAgent", "ClaudeCode", "OpenCode", "KTransformers", "Ollama"}
    found = forbidden & set(names)
    assert not found, f"backend.ral exports forbidden concrete runtime names: {found}"
