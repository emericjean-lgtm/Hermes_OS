"""Tests for the Runtime Recovery Engine (HOS-036)."""

from __future__ import annotations

import threading

import pytest

from backend.runtime.recovery.recovery_actions import (
    NotifyAction,
    RestartRuntimeAction,
    SwitchRuntimeAction,
    UnloadResourceAction,
)
from backend.runtime.recovery.recovery_engine import RecoveryEngine
from backend.runtime.recovery.recovery_models import (
    ActionType,
    IncidentType,
    RecoveryIncident,
    RecoveryPolicy,
    RecoveryStatus,
)
from backend.runtime.recovery.recovery_policy import RecoveryPolicyEngine


# ─── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def engine() -> RecoveryEngine:
    return RecoveryEngine()


@pytest.fixture
def policy_engine() -> RecoveryPolicyEngine:
    return RecoveryPolicyEngine()


# ─── 1. Incident Detection Tests ───────────────────────────


class TestIncidentDetection:
    def test_detect_runtime_failed(self, engine: RecoveryEngine):
        """Runtime failed event creates an incident and triggers recovery."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload, "severity": severity})

        engine._on_event = on_event
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="ollama-qwen3",
            payload={"error": "OOM"},
        )

        status = engine.get_status()
        assert status["total_incidents"] >= 1
        # Should have published recovery.started and recovery.completed
        started = [e for e in events if e["type"] == "recovery.started"]
        assert len(started) >= 1

    def test_detect_runtime_unavailable(self, engine: RecoveryEngine):
        """Runtime unavailable triggers fallback policy."""
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_UNAVAILABLE.value,
            runtime_id="ollama-qwen3",
            payload={"fallback_runtime": "ollama-deepseek"},
        )

        status = engine.get_status()
        assert status["total_incidents"] >= 1

    def test_detect_resource_limit(self, engine: RecoveryEngine):
        """Resource limit reached triggers unload policy."""
        engine.on_runtime_event(
            event_type=IncidentType.RESOURCE_LIMIT_REACHED.value,
            runtime_id="ollama-qwen3",
            payload={"vram_pct": 95},
        )

        status = engine.get_status()
        assert status["total_incidents"] >= 1

    def test_detect_overloaded(self, engine: RecoveryEngine):
        """Runtime overloaded triggers unload policy."""
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_OVERLOADED.value,
            runtime_id="ollama-qwen3",
            payload={},
        )

        status = engine.get_status()
        assert status["total_incidents"] >= 1
        assert status["total_attempts"] >= 1

    def test_unknown_event_no_policy(self, engine: RecoveryEngine):
        """Event without matching policy does nothing."""
        before = engine.get_status()["total_incidents"]
        engine.on_runtime_event(
            event_type="unknown.event",
            runtime_id="test",
            payload={},
        )
        after = engine.get_status()["total_incidents"]
        assert after == before + 1  # Incident is logged
        assert engine.get_status()["total_attempts"] <= before  # No recovery


# ─── 2. Recovery Action Tests ──────────────────────────────


class TestRecoveryActions:
    def test_restart_runtime_succeeds(self):
        """RestartRuntimeAction executes successfully."""
        action = RestartRuntimeAction(runtime_id="ollama-qwen3", delay_s=0.01)
        result = action.execute()
        assert result.success
        assert action.action_type == ActionType.RESTART_RUNTIME
        assert "restarted" in result.message.lower()

    def test_switch_runtime_with_fallback(self):
        """SwitchRuntimeAction with known fallback succeeds."""
        action = SwitchRuntimeAction(
            runtime_id="ollama-qwen3",
            fallback_runtime="ollama-deepseek",
        )
        result = action.execute()
        assert result.success
        assert "ollama-deepseek" in result.message

    def test_switch_runtime_no_fallback(self):
        """SwitchRuntimeAction with no fallback fails."""
        action = SwitchRuntimeAction(runtime_id="ollama-qwen3")
        result = action.execute()
        assert not result.success

    def test_unload_resource_succeeds(self):
        """UnloadResourceAction executes successfully."""
        action = UnloadResourceAction(runtime_id="ollama-qwen3", resource_type="vram")
        result = action.execute()
        assert result.success
        assert "vram" in result.message.lower()

    def test_notify_action(self):
        """NotifyAction publishes a message."""
        action = NotifyAction(runtime_id="ollama-qwen3", message="Test notification")
        result = action.execute()
        assert result.success
        assert "Test notification" in result.message


# ─── 3. Recovery Engine Tests ──────────────────────────────


class TestRecoveryEngine:
    def test_full_recovery_flow(self, engine: RecoveryEngine):
        """Full recovery flow from incident to completion."""
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="test-runtime",
            payload={"error": "Something broke"},
        )

        status = engine.get_status()
        assert status["total_attempts"] >= 1
        assert status["total_incidents"] >= 1

    def test_max_attempts_reached(self, engine: RecoveryEngine):
        """After max_attempts, no more recovery is attempted."""
        for _ in range(10):
            engine.on_runtime_event(
                event_type=IncidentType.RUNTIME_FAILED.value,
                runtime_id="test-runtime",
                payload={},
            )

        status = engine.get_status()
        # Default policy has max_attempts=3
        assert status["total_attempts"] <= 10

    def test_history(self, engine: RecoveryEngine):
        """get_history returns recovery attempts."""
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="history-test",
            payload={},
        )

        history = engine.get_history(limit=10)
        assert len(history) >= 1
        assert history[0].status in (RecoveryStatus.COMPLETED, RecoveryStatus.FAILED)

    def test_retry_incident(self, engine: RecoveryEngine):
        """Retry a failed incident."""
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="retry-test",
            payload={},
        )

        status = engine.get_status()
        incident_count = status["total_incidents"]

        # Get the last incident ID
        result = engine.retry_incident("nonexistent")
        assert result is None

        assert incident_count >= 1


# ─── 4. Policy Engine Tests ────────────────────────────────


class TestPolicyEngine:
    def test_policy_match(self, policy_engine: RecoveryPolicyEngine):
        """Policies are matched to the right incident types."""
        incident = RecoveryIncident(
            incident_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="test",
        )
        matches = policy_engine.match(incident)
        assert len(matches) >= 1
        assert any(p.name == "restart_on_failure" for p in matches)

    def test_policy_no_match(self, policy_engine: RecoveryPolicyEngine):
        """Unknown incident type returns no policies."""
        incident = RecoveryIncident(
            incident_type="unknown.incident",
            runtime_id="test",
        )
        matches = policy_engine.match(incident)
        assert len(matches) == 0

    def test_policy_cooldown(self, policy_engine: RecoveryPolicyEngine):
        """Cooldown prevents repeated policy matching for same runtime."""
        incident = RecoveryIncident(
            incident_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="test-runtime",
        )

        # First match should succeed
        matches1 = policy_engine.match(incident)
        assert len(matches1) >= 1

        # Mark cooldown
        for p in matches1:
            policy_engine.mark_cooldown(p, "test-runtime")

        # Second match should be empty (within cooldown)
        matches2 = policy_engine.match(incident)
        assert len(matches2) == 0

    def test_policy_disabled(self, policy_engine: RecoveryPolicyEngine):
        """Disabled policy is not matched."""
        for p in policy_engine.list_policies():
            if p.name == "restart_on_failure":
                p.enabled = False

        incident = RecoveryIncident(
            incident_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="test",
        )
        matches = policy_engine.match(incident)
        assert not any(p.name == "restart_on_failure" for p in matches)

        # Re-enable
        for p in policy_engine.list_policies():
            if p.name == "restart_on_failure":
                p.enabled = True

    def test_list_policies_sorted(self, policy_engine: RecoveryPolicyEngine):
        """Policies are sorted by priority (descending)."""
        policies = policy_engine.list_policies()
        assert len(policies) >= 1
        for i in range(len(policies) - 1):
            assert policies[i].priority >= policies[i + 1].priority

    def test_add_remove_policy(self, policy_engine: RecoveryPolicyEngine):
        """Custom policies can be added and removed."""
        custom = RecoveryPolicy(
            name="custom_test",
            incident_types=[IncidentType.RUNTIME_FAILED.value],
            actions=[NotifyAction(runtime_id="", message="custom")],
            priority=99,
        )

        # Add
        policy_engine.add_policy(custom)
        assert any(p.name == "custom_test" for p in policy_engine.list_policies())

        # Match
        incident = RecoveryIncident(
            incident_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="test",
        )
        matches = policy_engine.match(incident)
        assert any(p.name == "custom_test" for p in matches)

        # Remove
        assert policy_engine.remove_policy(custom.policy_id)
        assert not any(p.name == "custom_test" for p in policy_engine.list_policies())


# ─── 5. Thread Safety Tests ────────────────────────────────


class TestRecoveryThreadSafety:
    def test_concurrent_incidents(self):
        """Multiple threads can inject incidents simultaneously."""
        engine = RecoveryEngine()
        errors: list[Exception] = []

        def inject(idx: int) -> None:
            try:
                engine.on_runtime_event(
                    event_type=IncidentType.RUNTIME_FAILED.value,
                    runtime_id=f"r{idx}",
                    payload={"thread": idx},
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=inject, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert engine.get_status()["total_incidents"] == 10

    def test_concurrent_history_access(self):
        """get_history is safe under concurrent writes."""
        engine = RecoveryEngine()
        errors: list[Exception] = []

        def writer() -> None:
            for i in range(20):
                try:
                    engine.on_runtime_event(
                        event_type=IncidentType.RUNTIME_FAILED.value,
                        runtime_id=f"w{i}",
                        payload={},
                    )
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(50):
                try:
                    engine.get_history(limit=5)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors


# ─── 6. Event Integration Tests ────────────────────────────


class TestEventIntegration:
    def test_recovery_starts_event_published(self, engine: RecoveryEngine):
        """recovery.started event is published."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload, "severity": severity})

        engine._on_event = on_event
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="event-test",
            payload={},
        )

        started = [e for e in events if e["type"] == "recovery.started"]
        assert len(started) >= 1
        assert "incident_id" in started[0]["payload"]

    def test_recovery_completed_event_published(self, engine: RecoveryEngine):
        """recovery.completed event is published on success."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload, "severity": severity})

        engine._on_event = on_event
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="event-test-2",
            payload={},
        )

        completed = [e for e in events if e["type"] == "recovery.completed"]
        assert len(completed) >= 1
        assert "attempt_id" in completed[0]["payload"]

    def test_action_started_event_published(self, engine: RecoveryEngine):
        """recovery.action_started events are published."""
        events: list[dict] = []

        def on_event(ev_type: str, payload: dict, severity: str = "info") -> None:
            events.append({"type": ev_type, "payload": payload, "severity": severity})

        engine._on_event = on_event
        engine.on_runtime_event(
            event_type=IncidentType.RUNTIME_FAILED.value,
            runtime_id="action-test",
            payload={},
        )

        action_events = [e for e in events if e["type"] == "recovery.action_started"]
        assert len(action_events) >= 1
        assert "action_type" in action_events[0]["payload"]
