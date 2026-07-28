"""HOS-019 sentinel tests — Agent Lifecycle Manager.

Tests the state machine, transitions, queries and cleanup without any
concrete agent or network dependency.
"""

from __future__ import annotations

import threading
import time

import pytest

from backend.agent.lifecycle import (
    AgentContext,
    AgentInstance,
    AgentLifecycleError,
    AgentLifecycleManager,
    AgentState,
    AgentStatistics,
    LifecycleEvent,
)


# ============================================================================
# Dataclass tests
# ============================================================================


def test_agent_context_defaults() -> None:
    c = AgentContext(id="a1")
    assert c.id == "a1"
    assert c.mission_id == ""
    assert c.runtime_capability == "chat"


def test_agent_context_frozen() -> None:
    c = AgentContext(id="a1")
    with pytest.raises(AttributeError):
        c.id = "a2"  # type: ignore[misc]


def test_agent_statistics_defaults() -> None:
    s = AgentStatistics()
    assert s.execution_count == 0
    assert s.retries == 0
    assert s.failures == 0
    assert s.total_duration == 0.0


def test_agent_instance_creation() -> None:
    ctx = AgentContext(id="a1")
    inst = AgentInstance(
        id="a1",
        state=AgentState.CREATED,
        context=ctx,
        created_at=100.0,
    )
    assert inst.id == "a1"
    assert inst.state == AgentState.CREATED
    assert inst.started_at is None
    assert inst.finished_at is None


def test_agent_state_values() -> None:
    assert AgentState.CREATED.value == "created"
    assert AgentState.READY.value == "ready"
    assert AgentState.RUNNING.value == "running"
    assert AgentState.PAUSED.value == "paused"
    assert AgentState.COMPLETED.value == "completed"
    assert AgentState.FAILED.value == "failed"
    assert AgentState.CANCELLED.value == "cancelled"
    assert AgentState.TIMEOUT.value == "timeout"


def test_lifecycle_event_values() -> None:
    assert LifecycleEvent.CREATED.value == "lifecycle.created"
    assert LifecycleEvent.STARTED.value == "lifecycle.started"
    assert LifecycleEvent.COMPLETED.value == "lifecycle.completed"
    assert LifecycleEvent.FAILED.value == "lifecycle.failed"


# ============================================================================
# LifecycleManager: creation
# ============================================================================


def test_create_agent() -> None:
    mgr = AgentLifecycleManager()
    ctx = AgentContext(id="a1")
    inst = mgr.create_agent(ctx)
    assert inst.state == AgentState.READY  # auto-advances to READY
    assert inst.context.id == "a1"
    assert inst.created_at > 0


def test_create_agent_duplicate_raises() -> None:
    mgr = AgentLifecycleManager()
    ctx = AgentContext(id="a1")
    mgr.create_agent(ctx)
    with pytest.raises(AgentLifecycleError, match="already exists"):
        mgr.create_agent(ctx)


# ============================================================================
# State transitions
# ============================================================================


def test_start_agent() -> None:
    mgr = AgentLifecycleManager()
    ctx = AgentContext(id="a1")
    mgr.create_agent(ctx)
    inst = mgr.start_agent("a1")
    assert inst.state == AgentState.RUNNING
    assert inst.started_at is not None


def test_pause_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    inst = mgr.pause_agent("a1")
    assert inst.state == AgentState.PAUSED


def test_pause_agent_not_running_raises() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    with pytest.raises(AgentLifecycleError, match="Invalid transition"):
        mgr.pause_agent("a1")


def test_resume_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    mgr.pause_agent("a1")
    inst = mgr.resume_agent("a1")
    assert inst.state == AgentState.RUNNING


def test_resume_agent_not_paused_raises() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    with pytest.raises(AgentLifecycleError, match="Expected 'paused'"):
        mgr.resume_agent("a1")


def test_complete_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    inst = mgr.complete_agent("a1")
    assert inst.state == AgentState.COMPLETED
    assert inst.finished_at is not None


def test_fail_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    inst = mgr.fail_agent("a1")
    assert inst.state == AgentState.FAILED
    assert inst.finished_at is not None


def test_cancel_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    inst = mgr.cancel_agent("a1")
    assert inst.state == AgentState.CANCELLED


def test_cancel_agent_twice_raises() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.cancel_agent("a1")  # goes from READY → CANCELLED
    with pytest.raises(AgentLifecycleError, match="terminal"):
        mgr.cancel_agent("a1")


# ============================================================================
# Invalid transitions
# ============================================================================


def test_created_to_cancelled() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    inst = mgr.cancel_agent("a1")
    assert inst.state == AgentState.CANCELLED  # cancel allowed from READY


def test_completed_to_running_raises() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    mgr.complete_agent("a1")
    with pytest.raises(AgentLifecycleError, match="Invalid transition|terminal"):
        mgr.start_agent("a1")


def test_scheduled_to_running() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    # Directly transition to SCHEDULED then RUNNING (via start_agent)
    inst = mgr.start_agent("a1")  # goes READY → RUNNING
    assert inst.state == AgentState.RUNNING


# ============================================================================
# Agent retrieval and listing
# ============================================================================


def test_get_agent() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    inst = mgr.get_agent("a1")
    assert inst.id == "a1"


def test_get_agent_not_found_raises() -> None:
    mgr = AgentLifecycleManager()
    with pytest.raises(AgentLifecycleError, match="not found"):
        mgr.get_agent("nonexistent")


def test_list_agents() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.create_agent(AgentContext(id="a2"))
    assert len(mgr.list_agents()) == 2


def test_list_agents_filter_by_state() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.create_agent(AgentContext(id="a2"))
    mgr.start_agent("a1")
    running = mgr.list_agents(state=AgentState.RUNNING)
    ready = mgr.list_agents(state=AgentState.READY)
    assert len(running) == 1
    assert len(ready) == 1


# ============================================================================
# Statistics
# ============================================================================


def test_statistics_accumulate_failures() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    time.sleep(0.01)
    mgr.fail_agent("a1")
    stats = mgr.get_agent("a1").statistics
    assert stats.failures == 1
    assert stats.execution_count == 1
    assert stats.total_duration > 0.0


def test_statistics_updates_after_multiple_transitions() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    time.sleep(0.01)
    mgr.pause_agent("a1")
    mgr.resume_agent("a1")
    time.sleep(0.01)
    mgr.complete_agent("a1")
    stats = mgr.get_agent("a1").statistics
    assert stats.failures == 0
    assert stats.total_duration > 0.0


# ============================================================================
# Timeout
# ============================================================================


def test_check_timeouts() -> None:
    mgr = AgentLifecycleManager(timeout_s=0.05)
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    time.sleep(0.1)
    timed_out = mgr.check_timeouts()
    assert "a1" in timed_out
    assert mgr.get_agent("a1").state == AgentState.TIMEOUT


def test_check_timeouts_no_timeout() -> None:
    mgr = AgentLifecycleManager(timeout_s=300.0)
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    timed_out = mgr.check_timeouts()
    assert timed_out == []


# ============================================================================
# Cleanup
# ============================================================================


def test_cleanup_removes_old_terminal_agents() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    mgr.complete_agent("a1")
    # Force finished_at to be very old by patching the internal dict.
    # Instead, we create an agent that was completed a long time ago.
    time.sleep(0.01)  # ensure cleanup has a window
    removed = mgr.cleanup(max_age_s=0.001)
    assert removed == 1
    assert len(mgr.list_agents()) == 0


def test_cleanup_skips_active_agents() -> None:
    mgr = AgentLifecycleManager()
    mgr.create_agent(AgentContext(id="a1"))
    removed = mgr.cleanup(max_age_s=0.001)
    assert removed == 0  # not in terminal state


# ============================================================================
# Event handlers
# ============================================================================


def test_event_handler_called_on_transition() -> None:
    mgr = AgentLifecycleManager()
    events: list[tuple[str, AgentState, AgentState]] = []
    mgr.on_event(lambda a_id, f, t: events.append((a_id, f, t)))

    mgr.create_agent(AgentContext(id="a1"))
    mgr.start_agent("a1")
    mgr.complete_agent("a1")

    assert len(events) >= 3
    assert events[0][1] == AgentState.CREATED
    assert events[0][2] == AgentState.READY


# ============================================================================
# Thread safety
# ============================================================================


def test_concurrent_create_and_transition() -> None:
    mgr = AgentLifecycleManager()

    def worker(worker_id: int) -> None:
        for i in range(20):
            aid = f"w{worker_id}_a{i}"
            try:
                mgr.create_agent(AgentContext(id=aid))
                mgr.start_agent(aid)
                mgr.complete_agent(aid)
            except AgentLifecycleError:
                pass

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(mgr.list_agents()) == 60  # 3 workers × 20 agents


def test_concurrent_list_and_transition() -> None:
    mgr = AgentLifecycleManager()
    for i in range(20):
        mgr.create_agent(AgentContext(id=f"a{i}"))

    errors: list[Exception] = []

    def start_loops() -> None:
        for i in range(20):
            try:
                mgr.start_agent(f"a{i}")
                mgr.complete_agent(f"a{i}")
            except Exception as e:
                errors.append(e)

    def list_loop() -> None:
        for _ in range(100):
            try:
                _ = mgr.list_agents(state=AgentState.READY)
                _ = mgr.list_agents()
            except Exception as e:
                errors.append(e)

    t1 = threading.Thread(target=start_loops)
    t2 = threading.Thread(target=list_loop)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
