"""Tests for Security, Sandbox & Trust Layer (HOS-057).

Covers: permissions, trust scoring, threat detection, isolation,
policy integration, workspace integration, tool integration,
EventBus, thread safety, and API routes.
"""

import threading
import pytest

from backend.security.security_models import (
    AgentTrustScore,
    CapabilityToken,
    IsolationLevel,
    IsolationProfile,
    Permission,
    PermissionAction,
    ResourceType,
    SECURITY_EVENTS,
    SecurityEvent,
    SecurityPolicy,
    ThreatDetection,
    ThreatLevel,
    TrustLevel,
)
from backend.security.permission_manager import PermissionManager
from backend.security.agent_trust_engine import AgentTrustEngine
from backend.security.threat_detector import ThreatDetector
from backend.security.isolation_manager import IsolationManager
from backend.security.security_engine import SecurityEngine
from backend.security.routes import (
    handle_check_access,
    handle_grant_permission,
    handle_get_trust,
    handle_get_status,
    handle_get_policies,
    handle_get_events,
    handle_get_threats,
    get_engine,
)


# ======================================================================
# 1. Models
# ======================================================================

class TestSecurityModels:
    """Data model integrity."""

    def test_security_policy_to_dict(self):
        p = SecurityPolicy(policy_id="p1", name="Test Policy",
                          resource_type=ResourceType.AGENT, action=PermissionAction.ALLOW)
        d = p.to_dict()
        assert d["policy_id"] == "p1"
        assert d["action"] == "allow"

    def test_permission_expired(self):
        from datetime import datetime, timedelta, timezone
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        p = Permission(permission_id="p1", resource_type=ResourceType.TOOL,
                       resource_id="exec", expires_at=expired)
        assert p.is_expired() is True

    def test_permission_not_expired(self):
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        p = Permission(permission_id="p2", resource_type=ResourceType.TOOL,
                       resource_id="exec", expires_at=future)
        assert p.is_expired() is False

    def test_capability_token_is_valid(self):
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        t = CapabilityToken(token_id="t1", principal_id="agent1",
                           capabilities=["read"], expires_at=future)
        assert t.is_valid() is True

    def test_capability_token_expired(self):
        from datetime import datetime, timedelta, timezone
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        t = CapabilityToken(token_id="t2", expires_at=past)
        assert t.is_valid() is False

    def test_agent_trust_score_defaults(self):
        s = AgentTrustScore(agent_id="test")
        assert s.score == 50.0
        assert s.level == TrustLevel.UNKNOWN
        assert s.recent_behavior == 1.0

    def test_threat_detection_levels(self):
        for level in ThreatLevel:
            t = ThreatDetection(threat_id=f"t_{level.value}", level=level)
            assert t.level == level

    def test_security_event_to_dict(self):
        e = SecurityEvent(event_id="e1", event_type="test", source="test",
                         principal_id="agent1", message="Test event")
        d = e.to_dict()
        assert d["event_type"] == "test"

    def test_isolation_profile_defaults(self):
        p = IsolationProfile(profile_id="p1", level=IsolationLevel.MEDIUM)
        assert p.network_blocked is True
        assert p.max_memory_mb == 512
        assert p.max_duration_s == 3600

    def test_resource_type_values(self):
        assert ResourceType.AGENT.value == "agent"
        assert ResourceType.TOOL.value == "tool"
        assert ResourceType.FILE.value == "file"

    def test_trust_level_order(self):
        levels = [TrustLevel.UNKNOWN, TrustLevel.LOW, TrustLevel.MEDIUM, TrustLevel.HIGH, TrustLevel.VERIFIED]
        assert len(levels) == 5


# ======================================================================
# 2. Permission Manager
# ======================================================================

class TestPermissionManager:
    """Permission management."""

    def test_grant_permission(self):
        pm = PermissionManager()
        perm = pm.grant_permission("agent1", ResourceType.TOOL, "exec", True)
        assert perm.principal_id == "agent1"
        assert perm.resource_type == ResourceType.TOOL

    def test_check_permission_exists(self):
        pm = PermissionManager()
        pm.grant_permission("agent1", ResourceType.TOOL, "exec", True)
        assert pm.check_permission("agent1", ResourceType.TOOL, "exec") is True

    def test_check_permission_missing(self):
        pm = PermissionManager()
        assert pm.check_permission("agent1", ResourceType.TOOL, "exec") is False

    def test_revoke_permission(self):
        pm = PermissionManager()
        pm.grant_permission("agent1", ResourceType.TOOL, "exec", True)
        assert pm.revoke_permission("agent1", ResourceType.TOOL, "exec") is True
        assert pm.check_permission("agent1", ResourceType.TOOL, "exec") is False

    def test_list_permissions_by_principal(self):
        pm = PermissionManager()
        pm.grant_permission("agent1", ResourceType.TOOL, "exec")
        pm.grant_permission("agent1", ResourceType.WORKSPACE, "ws1")
        pm.grant_permission("agent2", ResourceType.TOOL, "exec")
        perms = pm.list_permissions("agent1")
        assert len(perms) == 2

    def test_evaluate_policy_allow(self):
        pm = PermissionManager()
        pm.add_policy(SecurityPolicy(policy_id="p1", name="Allow all",
                                     resource_type=ResourceType.TOOL, action=PermissionAction.ALLOW))
        action, policy = pm.evaluate_policies("agent1", ResourceType.TOOL, "exec")
        assert action == PermissionAction.ALLOW

    def test_evaluate_policy_deny(self):
        pm = PermissionManager()
        pm.add_policy(SecurityPolicy(policy_id="p2", name="Deny exec",
                                     resource_type=ResourceType.TOOL, action=PermissionAction.DENY))
        action, _ = pm.evaluate_policies("agent1", ResourceType.TOOL, "exec")
        assert action == PermissionAction.DENY

    def test_evaluate_policy_review(self):
        pm = PermissionManager()
        pm.add_policy(SecurityPolicy(policy_id="p3", name="Review",
                                     resource_type=ResourceType.TOOL, action=PermissionAction.REVIEW))
        action, _ = pm.evaluate_policies("agent1", ResourceType.TOOL, "exec")
        assert action == PermissionAction.REVIEW

    def test_policy_priority(self):
        pm = PermissionManager()
        pm.add_policy(SecurityPolicy(policy_id="p1", name="Low", resource_type=ResourceType.TOOL,
                                     action=PermissionAction.ALLOW, priority=0))
        pm.add_policy(SecurityPolicy(policy_id="p2", name="High", resource_type=ResourceType.TOOL,
                                     action=PermissionAction.DENY, priority=100))
        action, matched = pm.evaluate_policies("agent1", ResourceType.TOOL, "exec")
        assert action == PermissionAction.DENY  # Higher priority wins
        assert matched.policy_id == "p2"

    def test_policy_list_by_type(self):
        pm = PermissionManager()
        pm.add_policy(SecurityPolicy(policy_id="p1", name="Tool", resource_type=ResourceType.TOOL))
        pm.add_policy(SecurityPolicy(policy_id="p2", name="Agent", resource_type=ResourceType.AGENT))
        tools = pm.get_policies(resource_type=ResourceType.TOOL)
        assert len(tools) == 1

    def test_history_tracked(self):
        pm = PermissionManager()
        pm.grant_permission("agent1", ResourceType.TOOL, "exec")
        pm.revoke_permission("agent1", ResourceType.TOOL, "exec")
        history = pm.get_history()
        assert len(history) >= 2


# ======================================================================
# 3. Agent Trust Engine
# ======================================================================

class TestAgentTrustEngine:
    """Trust scoring."""

    def test_new_agent_default(self):
        te = AgentTrustEngine()
        score = te.get_score("agent1")
        assert score.score == 50.0
        assert score.level == TrustLevel.UNKNOWN

    def test_record_success_boosts_score(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True)
        score = te.get_score("agent1")
        assert score.score > 50.0

    def test_record_failure_reduces_score(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True)   # 1/1 = 100% boost
        s1 = te.get_score("agent1").score
        te.record_result("agent1", False)  # 1/2 = 50%
        s2 = te.get_score("agent1").score
        assert s2 < s1

    def test_policy_violation_reduces(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True, quality=1.0)
        s1 = te.get_score("agent1").score
        te.record_policy_violation("agent1")
        s2 = te.get_score("agent1").score
        assert s2 < s1

    def test_human_approval_boosts(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True)
        s1 = te.get_score("agent1").score
        te.record_human_approval("agent1")
        s2 = te.get_score("agent1").score
        assert s2 >= s1

    def test_trust_level_verified(self):
        te = AgentTrustEngine()
        for _ in range(10):
            te.record_result("agent1", True)
        score = te.get_score("agent1")
        assert score.level in (TrustLevel.HIGH, TrustLevel.VERIFIED)

    def test_trust_level_low(self):
        te = AgentTrustEngine()
        for _ in range(5):
            te.record_result("agent1", False)
        score = te.get_score("agent1")
        assert score.level in (TrustLevel.LOW, TrustLevel.UNKNOWN)

    def test_meets_threshold(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True)
        assert te.meets_threshold("agent1", TrustLevel.LOW) is True
        assert te.meets_threshold("agent1", TrustLevel.VERIFIED) is False

    def test_get_threshold_values(self):
        te = AgentTrustEngine()
        assert te.get_threshold(TrustLevel.LOW) == 20
        assert te.get_threshold(TrustLevel.MEDIUM) == 40
        assert te.get_threshold(TrustLevel.HIGH) == 70

    def test_get_all_scores(self):
        te = AgentTrustEngine()
        te.record_result("agent1", True)
        te.record_result("agent2", False)
        assert len(te.get_all_scores()) == 2

    def test_notify_on_update(self):
        te = AgentTrustEngine()
        updates = []
        te.on_trust_update(lambda aid, s: updates.append(aid))
        te.record_result("agent1", True)
        assert len(updates) == 1
        assert updates[0] == "agent1"


# ======================================================================
# 4. Threat Detector
# ======================================================================

class TestThreatDetector:
    """Threat detection."""

    def test_file_access_allowed(self):
        td = ThreatDetector()
        threat = td.check_file_access("agent1", "/tmp/workspace/file.py", ["/tmp/workspace"])
        assert threat is None

    def test_file_access_denied(self):
        td = ThreatDetector()
        threat = td.check_file_access("agent1", "/etc/passwd", ["/tmp/workspace"])
        assert threat is not None
        assert threat.threat_type == "unauthorized_file_access"
        assert threat.level == ThreatLevel.MEDIUM

    def test_resource_usage_normal(self):
        td = ThreatDetector()
        threat = td.check_resource_usage("agent1", "cpu", 100)
        assert threat is None

    def test_resource_usage_excessive(self):
        td = ThreatDetector()
        for _ in range(5):
            td.check_resource_usage("agent1", "cpu", 800)
        threat = td.check_resource_usage("agent1", "cpu", 800)
        assert threat is not None
        assert threat.threat_type == "excessive_resource_usage"

    def test_suspicious_tool_detected(self):
        td = ThreatDetector()
        threat = td.check_tool_call("agent1", "exec", {"cmd": "ls"})
        assert threat is not None
        assert threat.threat_type == "suspicious_tool_call"

    def test_normal_tool_not_detected(self):
        td = ThreatDetector()
        threat = td.check_tool_call("agent1", "read_file", {"path": "/tmp"})
        # Normal tools should not trigger without exec/shell in name
        assert threat is None
        threat2 = td.check_tool_call("agent1", "list_dir", {"path": "/tmp"})
        assert threat2 is None

    def test_sandbox_violation(self):
        td = ThreatDetector()
        threat = td.check_sandbox_violation("agent1", "network_escape", {"ip": "10.0.0.1"})
        assert threat.level == ThreatLevel.CRITICAL
        assert threat.mitigated is False

    def test_mitigate_threat(self):
        td = ThreatDetector()
        threat = td.check_sandbox_violation("agent1", "escape", {})
        ok = td.mitigate_threat(threat.threat_id, "blocked")
        assert ok is True

    def test_get_threats_by_level(self):
        td = ThreatDetector()
        td.check_sandbox_violation("agent1", "escape", {})
        td.check_file_access("agent1", "/etc/passwd", ["/tmp"])
        threats = td.get_threats(level=ThreatLevel.CRITICAL)
        assert len(threats) == 1

    def test_get_threats_by_agent(self):
        td = ThreatDetector()
        td.check_file_access("agent1", "/etc/passwd", ["/tmp"])
        td.check_file_access("agent2", "/etc/shadow", ["/tmp"])
        threats = td.get_threats(principal_id="agent1")
        assert len(threats) == 1
        assert threats[0].principal_id == "agent1"

    def test_stats_tracked(self):
        td = ThreatDetector()
        td.check_file_access("agent1", "/etc/passwd", ["/tmp"])
        td.check_sandbox_violation("agent1", "escape", {})
        stats = td.stats()
        assert stats["total_threats"] == 2


# ======================================================================
# 5. Isolation Manager
# ======================================================================

class TestIsolationManager:
    """Isolation profiles and sessions."""

    def test_create_profile(self):
        im = IsolationManager()
        p = im.create_profile(IsolationLevel.MEDIUM, allowed_files=["/tmp"])
        assert p.profile_id.startswith("iso_")
        assert p.level == IsolationLevel.MEDIUM

    def test_get_profile(self):
        im = IsolationManager()
        p = im.create_profile()
        assert im.get_profile(p.profile_id) is p

    def test_get_profile_for_level(self):
        im = IsolationManager()
        p = im.get_profile_for_level(IsolationLevel.HIGH)
        assert p.level == IsolationLevel.HIGH

    def test_start_session(self):
        im = IsolationManager()
        p = im.create_profile()
        assert im.start_session("session1", p.profile_id) is True

    def test_end_session(self):
        im = IsolationManager()
        p = im.create_profile()
        im.start_session("s1", p.profile_id)
        assert im.end_session("s1") is True
        assert im.get_session_profile("s1") is None

    def test_validate_file_read_allowed(self):
        im = IsolationManager()
        p = im.create_profile(allowed_files=["/tmp/workspace"])
        im.start_session("s1", p.profile_id)
        assert im.validate_operation("s1", "file_read", "/tmp/workspace/file.py") is True

    def test_validate_file_read_denied(self):
        im = IsolationManager()
        p = im.create_profile(allowed_files=["/tmp/workspace"])
        im.start_session("s1", p.profile_id)
        assert im.validate_operation("s1", "file_read", "/etc/passwd") is False

    def test_validate_tool_allowed(self):
        im = IsolationManager()
        p = im.create_profile(allowed_tools=["read", "write"])
        im.start_session("s1", p.profile_id)
        assert im.validate_operation("s1", "tool", "read") is True

    def test_validate_tool_denied(self):
        im = IsolationManager()
        p = im.create_profile(allowed_tools=["read"])
        im.start_session("s1", p.profile_id)
        assert im.validate_operation("s1", "tool", "exec") is False

    def test_validate_network_blocked(self):
        im = IsolationManager()
        # Create profile with blocked networks explicitly
        p = im.create_profile(IsolationLevel.HIGH, blocked_networks=["*"])
        im.start_session("s1", p.profile_id)
        assert im.validate_operation("s1", "network", "10.0.0.1") is False

    def test_record_violation(self):
        im = IsolationManager()
        im.record_violation("s1", "file_read", "/etc/passwd", "Unauthorized access")
        violations = im.get_violations("s1")
        assert len(violations) == 1

    def test_stats(self):
        im = IsolationManager()
        im.create_profile(IsolationLevel.LOW)
        im.create_profile(IsolationLevel.HIGH)
        stats = im.stats()
        assert stats["total_profiles"] == 2


# ======================================================================
# 6. Security Engine
# ======================================================================

class TestSecurityEngine:
    """Integrated security pipeline."""

    def test_get_status(self):
        se = SecurityEngine()
        status = se.get_status()
        assert "permissions" in status
        assert "trust" in status
        assert "threats" in status
        assert "isolation" in status

    def test_check_access_policy_denied(self):
        se = SecurityEngine()
        # No policies = default DENY
        result = se.check_access("agent1", ResourceType.TOOL, "exec")
        assert result["allowed"] is False

    def test_check_access_with_permission(self):
        se = SecurityEngine()
        # Add an ALLOW policy so the pipeline proceeds past policy evaluation
        se.permissions.add_policy(SecurityPolicy(
            policy_id="allow_all", name="Allow all",
            resource_type=ResourceType.TOOL, action=PermissionAction.ALLOW,
        ))
        se.permissions.grant_permission("agent1", ResourceType.TOOL, "exec")
        se.trust.record_result("agent1", True)
        result = se.check_access("agent1", ResourceType.TOOL, "exec")
        assert result["allowed"] is True

    def test_check_access_denied_low_trust(self):
        se = SecurityEngine()
        se.permissions.grant_permission("agent1", ResourceType.TOOL, "exec")
        for _ in range(5):
            se.trust.record_result("agent1", False)
        result = se.check_access("agent1", ResourceType.TOOL, "exec")
        assert result["allowed"] is False

    def test_check_access_policy_overrides(self):
        se = SecurityEngine()
        se.permissions.grant_permission("agent1", ResourceType.TOOL, "exec")
        se.permissions.add_policy(SecurityPolicy(policy_id="p1", name="Deny all",
                                                 resource_type=ResourceType.TOOL,
                                                 action=PermissionAction.DENY))
        result = se.check_access("agent1", ResourceType.TOOL, "exec")
        assert result["allowed"] is False
        assert "Policy denied" in result["reason"]

    def test_check_access_review_required(self):
        se = SecurityEngine()
        se.permissions.add_policy(SecurityPolicy(policy_id="p1", name="Review all",
                                                 resource_type=ResourceType.TOOL,
                                                 action=PermissionAction.REVIEW))
        result = se.check_access("agent1", ResourceType.TOOL, "exec")
        assert result["requires_review"] is True

    def test_events_published(self):
        events = []
        se = SecurityEngine(on_event=lambda t, p, **kw: events.append(t))
        se.check_access("agent1", ResourceType.TOOL, "exec")
        assert SECURITY_EVENTS["permission_denied"] in events

    def test_trust_update_event(self):
        events = []
        se = SecurityEngine(on_event=lambda t, p, **kw: events.append(t))
        se.trust.record_result("agent1", True)
        assert SECURITY_EVENTS["agent_trust_updated"] in events


# ======================================================================
# 7. API Routes
# ======================================================================

class TestAPIRoutes:
    """API endpoint functions."""

    def test_get_status(self):
        result = handle_get_status()
        assert "permissions" in result
        assert "trust" in result

    def test_get_policies(self):
        policies = handle_get_policies()
        assert isinstance(policies, list)

    def test_grant_permission(self):
        result = handle_grant_permission({
            "principal_id": "agent1", "resource_type": "tool",
            "resource_id": "exec", "allowed": True,
        })
        assert result["principal_id"] == "agent1"
        assert result["allowed"] is True

    def test_check_access(self):
        result = handle_check_access({
            "principal_id": "agent1", "resource_type": "tool",
            "resource_id": "exec",
        })
        assert "allowed" in result

    def test_get_trust(self):
        get_engine().trust.record_result("agent1", True)
        result = handle_get_trust("agent1")
        assert result["agent_id"] == "agent1"
        assert "score" in result

    def test_get_events(self):
        events = handle_get_events()
        assert isinstance(events, list)


# ======================================================================
# 8. Thread Safety
# ======================================================================

class TestSecurityThreadSafety:
    """Concurrent operations."""

    def test_concurrent_permissions(self):
        pm = PermissionManager()
        errors = []
        def grant_and_check(i: int):
            try:
                pm.grant_permission(f"agent{i}", ResourceType.TOOL, "exec")
                pm.check_permission(f"agent{i}", ResourceType.TOOL, "exec")
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=grant_and_check, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_trust(self):
        te = AgentTrustEngine()
        errors = []
        def record_and_check(i: int):
            try:
                te.record_result("agent1", i % 2 == 0)
                te.get_score("agent1")
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=record_and_check, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_threats(self):
        td = ThreatDetector()
        errors = []
        def detect_and_check(i: int):
            try:
                td.check_file_access(f"agent{i}", "/etc/passwd", ["/tmp"])
                td.get_threats()
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=detect_and_check, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_isolation(self):
        im = IsolationManager()
        errors = []
        def create_and_check(i: int):
            try:
                p = im.create_profile()
                im.start_session(f"s{i}", p.profile_id)
                im.validate_operation(f"s{i}", "file_read", "/tmp")
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=create_and_check, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_security_engine(self):
        se = SecurityEngine()
        errors = []
        def check_access(i: int):
            try:
                se.check_access("agent1", ResourceType.TOOL, "exec")
            except Exception as e: errors.append(str(e))
        threads = [threading.Thread(target=check_access, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
