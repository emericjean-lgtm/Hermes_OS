"""Tests for the Human Approval & Policy Engine (HOS-046)."""

from __future__ import annotations

import threading

import pytest

from backend.policy.approval_engine import ApprovalEngine
from backend.policy.approval_queue import ApprovalQueue
from backend.policy.audit_log import AuditLog
from backend.policy.policy_engine import PolicyEngine
from backend.policy.policy_models import (
    ApprovalPriority,
    ApprovalStatus,
    AuditAction,
    EvaluationContext,
    PolicyDecision,
    PolicyRule,
    RuleCategory,
)
from backend.policy.rule_evaluator import RuleEvaluator


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def evaluator() -> RuleEvaluator:
    return RuleEvaluator()


@pytest.fixture
def approval_queue() -> ApprovalQueue:
    return ApprovalQueue()


@pytest.fixture
def approval_engine() -> ApprovalEngine:
    return ApprovalEngine()


@pytest.fixture
def audit_log() -> AuditLog:
    return AuditLog()


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine()


# ── Rule Evaluator Tests ─────────────────────────────────────

class TestRuleEvaluator:
    def test_builtins_registered(self, evaluator):
        rules = evaluator.get_all()
        assert len(rules) >= 8

    def test_git_merge_review_required(self, evaluator):
        ctx = EvaluationContext(operation="git_merge")
        decision, matched, reasons = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.REVIEW_REQUIRED

    def test_model_download_allowed(self, evaluator):
        ctx = EvaluationContext(operation="model_download")
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.ALLOW

    def test_system_modification_denied(self, evaluator):
        ctx = EvaluationContext(operation="system_modification")
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.DENY

    def test_high_risk_review(self, evaluator):
        ctx = EvaluationContext(operation="some_operation", risk_level=7.5)
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.REVIEW_REQUIRED

    def test_critical_risk_denied(self, evaluator):
        ctx = EvaluationContext(operation="some_operation", risk_level=9.5)
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.DENY

    def test_deny_overrides_review(self, evaluator):
        # Both high_risk (review) and critical_risk (deny) match
        ctx = EvaluationContext(operation="git_merge", risk_level=9.5)
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.DENY

    def test_register_custom_rule(self, evaluator):
        rule = PolicyRule(name="custom", condition="operation == 'test_op'",
                         decision=PolicyDecision.DENY)
        evaluator.register(rule)
        ctx = EvaluationContext(operation="test_op")
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.DENY

    def test_disabled_rule_ignored(self, evaluator):
        rules = evaluator.get_all()
        # Disable the git_merge rule
        for r in rules:
            if r.name == "git_merge_requires_review":
                r.enabled = False
        ctx = EvaluationContext(operation="git_merge")
        decision, _, _ = evaluator.evaluate(ctx)
        assert decision == PolicyDecision.ALLOW

    def test_get_by_category(self, evaluator):
        security = evaluator.get_by_category(RuleCategory.SECURITY)
        assert len(security) >= 3

    def test_stats(self, evaluator):
        stats = evaluator.stats()
        assert stats["total"] >= 8


# ── Approval Queue Tests ─────────────────────────────────────

class TestApprovalQueue:
    def test_enqueue(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        req = ApprovalRequest(operation="git_merge", title="Test")
        approval_queue.enqueue(req)
        assert approval_queue.get(req.approval_id) is not None

    def test_pending_sorted_by_priority(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        r1 = ApprovalRequest(operation="op1", priority=ApprovalPriority.LOW, title="L")
        r2 = ApprovalRequest(operation="op2", priority=ApprovalPriority.CRITICAL, title="C")
        r3 = ApprovalRequest(operation="op3", priority=ApprovalPriority.HIGH, title="H")
        approval_queue.enqueue(r1)
        approval_queue.enqueue(r2)
        approval_queue.enqueue(r3)
        pending = approval_queue.get_pending()
        assert pending[0].priority == ApprovalPriority.CRITICAL

    def test_update_status(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        req = ApprovalRequest(operation="test")
        approval_queue.enqueue(req)
        assert approval_queue.update_status(req.approval_id, ApprovalStatus.APPROVED)
        assert approval_queue.get(req.approval_id).status == ApprovalStatus.APPROVED

    def test_dequeue(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        req = ApprovalRequest(operation="test")
        approval_queue.enqueue(req)
        removed = approval_queue.dequeue(req.approval_id)
        assert removed is not None
        assert approval_queue.get(req.approval_id) is None

    def test_expire_stale(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        from datetime import datetime, timezone, timedelta
        req = ApprovalRequest(
            operation="test",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        approval_queue.enqueue(req)
        count = approval_queue.expire_stale()
        assert count >= 1
        assert approval_queue.get(req.approval_id).status == ApprovalStatus.EXPIRED

    def test_count_by_status(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        approval_queue.enqueue(ApprovalRequest(operation="1"))
        approval_queue.enqueue(ApprovalRequest(operation="2"))
        assert approval_queue.count_by_status(ApprovalStatus.PENDING) == 2

    def test_stats(self, approval_queue):
        from backend.policy.policy_models import ApprovalRequest
        approval_queue.enqueue(ApprovalRequest(operation="test"))
        stats = approval_queue.stats()
        assert stats["total"] >= 1


# ── Approval Engine Tests ────────────────────────────────────

class TestApprovalEngine:
    def test_request_and_approve(self, approval_engine):
        req = approval_engine.request_approval(
            "git_merge", "Merge feature", "Please review",
            EvaluationContext(operation="git_merge"),
        )
        assert req.status == ApprovalStatus.PENDING
        assert approval_engine.approve(req.approval_id, "admin", "LGTM")

    def test_reject(self, approval_engine):
        req = approval_engine.request_approval(
            "workspace_delete", "Delete ws", "Are you sure?",
            EvaluationContext(operation="workspace_delete"),
        )
        assert approval_engine.reject(req.approval_id, "admin", "Not now")
        assert approval_engine.get(req.approval_id).status == ApprovalStatus.REJECTED

    def test_delegate(self, approval_engine):
        req = approval_engine.request_approval(
            "git_merge", "Merge", "Review",
            EvaluationContext(operation="git_merge"),
        )
        assert approval_engine.delegate(req.approval_id, "admin", "reviewer")
        assert approval_engine.get(req.approval_id).status == ApprovalStatus.DELEGATED

    def test_cancel(self, approval_engine):
        req = approval_engine.request_approval(
            "test", "Test", "Desc", EvaluationContext(operation="test"),
        )
        assert approval_engine.cancel(req.approval_id)
        assert approval_engine.get(req.approval_id).status == ApprovalStatus.CANCELLED

    def test_multi_approval(self, approval_engine):
        req = approval_engine.request_approval(
            "git_merge", "Critical merge", "Needs 2 approvals",
            EvaluationContext(operation="git_merge"),
            required_approvals=2,
        )
        # First approval: not enough
        approval_engine.approve(req.approval_id, "admin1", "OK")
        assert approval_engine.get(req.approval_id).status == ApprovalStatus.PENDING
        # Second approval: now approved
        approval_engine.approve(req.approval_id, "admin2", "OK")
        assert approval_engine.get(req.approval_id).status == ApprovalStatus.APPROVED

    def test_get_pending(self, approval_engine):
        approval_engine.request_approval(
            "op1", "T1", "D1", EvaluationContext(operation="op1"),
        )
        pending = approval_engine.get_pending()
        assert len(pending) >= 1

    def test_check_expired(self, approval_engine):
        from datetime import datetime, timezone, timedelta
        from backend.policy.policy_models import ApprovalRequest
        req = ApprovalRequest(
            operation="test",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        approval_engine._queue.enqueue(req)
        count = approval_engine.check_expired()
        assert count >= 1


# ── Audit Log Tests ──────────────────────────────────────────

class TestAuditLog:
    def test_log_entry(self, audit_log):
        entry = audit_log.log(
            AuditAction.EVALUATED, agent_id="agent1",
            operation="git_merge", decision="review_required",
        )
        assert entry.audit_id
        assert audit_log.get(entry.audit_id) is not None

    def test_get_by_agent(self, audit_log):
        audit_log.log(AuditAction.EVALUATED, agent_id="agent1", operation="op1")
        audit_log.log(AuditAction.EVALUATED, agent_id="agent1", operation="op2")
        entries = audit_log.get_by_agent("agent1")
        assert len(entries) == 2

    def test_get_by_mission(self, audit_log):
        audit_log.log(AuditAction.EVALUATED, mission_id="m1", operation="op1")
        audit_log.log(AuditAction.APPROVED, mission_id="m1", operation="op2")
        entries = audit_log.get_by_mission("m1")
        assert len(entries) == 2

    def test_get_recent(self, audit_log):
        for i in range(10):
            audit_log.log(AuditAction.EVALUATED, operation=f"op{i}")
        recent = audit_log.get_recent(5)
        assert len(recent) == 5

    def test_query(self, audit_log):
        audit_log.log(AuditAction.EVALUATED, agent_id="a1", operation="git_merge")
        audit_log.log(AuditAction.APPROVED, agent_id="a1", operation="git_merge")
        results = audit_log.query(agent_id="a1", operation="git_merge")
        assert len(results) == 2

    def test_stats(self, audit_log):
        audit_log.log(AuditAction.EVALUATED, operation="test")
        stats = audit_log.stats()
        assert stats["total_entries"] >= 1


# ── Policy Engine Tests ──────────────────────────────────────

class TestPolicyEngine:
    def test_evaluate_allowed(self, engine):
        result = engine.evaluate(operation="model_download", agent_id="coder")
        assert result.decision == PolicyDecision.ALLOW
        assert not result.requires_approval

    def test_evaluate_denied(self, engine):
        result = engine.evaluate(operation="system_modification", agent_id="coder")
        assert result.decision == PolicyDecision.DENY

    def test_evaluate_review_required(self, engine):
        result = engine.evaluate(operation="git_merge", agent_id="coder",
                                 mission_id="m1")
        assert result.decision == PolicyDecision.REVIEW_REQUIRED
        assert result.requires_approval
        assert result.approval_id

    def test_is_allowed(self, engine):
        assert engine.is_allowed("model_download", "coder")
        assert not engine.is_allowed("system_modification", "coder")
        assert not engine.is_allowed("git_merge", "coder")

    def test_approve_review_workflow(self, engine):
        result = engine.evaluate(operation="git_merge", agent_id="coder")
        assert result.requires_approval
        assert engine.approve(result.approval_id, "admin", "Approved")
        req = engine.get_approval(result.approval_id)
        assert req.status == ApprovalStatus.APPROVED

    def test_reject_workflow(self, engine):
        result = engine.evaluate(operation="workspace_delete", agent_id="coder")
        assert engine.reject(result.approval_id, "admin", "Denied")

    def test_get_rules(self, engine):
        rules = engine.get_rules()
        assert len(rules) >= 8

    def test_audit_trail(self, engine):
        engine.evaluate(operation="model_download", agent_id="coder")
        engine.evaluate(operation="git_merge", agent_id="coder")
        entries = engine.get_recent_audit(5)
        assert len(entries) >= 2

    def test_pending_approvals(self, engine):
        engine.evaluate(operation="git_merge", agent_id="coder")
        pending = engine.get_pending_approvals()
        assert len(pending) >= 1

    def test_stats(self, engine):
        engine.evaluate(operation="model_download", agent_id="coder")
        stats = engine.stats()
        assert "rules" in stats
        assert "approvals" in stats
        assert "audit" in stats

    def test_example_mission_merge_approval(self, engine):
        """Full workflow: mission needs human approval before git merge."""
        # Step 1: Evaluate git_merge → requires approval
        result = engine.evaluate(
            operation="git_merge",
            agent_id="coder",
            mission_id="m1",
            node_id="n3",
            risk_level=3.0,
            details={"branch": "feature/auth", "target": "main"},
        )
        assert result.decision == PolicyDecision.REVIEW_REQUIRED
        assert result.requires_approval

        # Step 2: Admin approves
        ok = engine.approve(result.approval_id, "admin", "Reviewed: LGTM")
        assert ok

        # Step 3: Verify approval and audit
        req = engine.get_approval(result.approval_id)
        assert req.status == ApprovalStatus.APPROVED

        audit = engine.get_audit_log(mission_id="m1")
        assert len(audit) >= 2  # evaluated + approved


# ── Thread Safety Tests ──────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_evaluations(self, engine):
        errors = []

        def worker(idx):
            try:
                engine.evaluate(operation="model_download", agent_id=f"agent{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors

    def test_concurrent_approvals(self, approval_engine):
        errors = []

        def worker(idx):
            try:
                req = approval_engine.request_approval(
                    f"op{idx}", f"Title{idx}", "Desc",
                    EvaluationContext(operation=f"op{idx}"),
                )
                approval_engine.approve(req.approval_id, "admin")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors

    def test_concurrent_audit(self, audit_log):
        errors = []

        def worker(idx):
            try:
                audit_log.log(AuditAction.EVALUATED, agent_id=f"a{idx}",
                             operation=f"op{idx}")
            except Exception as e:
                errors.append(f"Worker {idx}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, errors
