"""Approval Engine for HOS-046.

Human approval workflow: approve, reject, comment, expire, delegate, multi-approval.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.policy.approval_queue import ApprovalQueue
from backend.policy.policy_models import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalStatus,
    EvaluationContext,
)


class ApprovalEngine:
    """Manages human approval workflows.

    Supports: approve, reject, comment, expire, delegate, multi-approval.
    Thread-safe.
    """

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._queue = ApprovalQueue(on_event=on_event)

    def request_approval(
        self,
        operation: str,
        title: str,
        description: str,
        context: EvaluationContext,
        required_approvals: int = 1,
        approvers: Optional[list[str]] = None,
        priority: ApprovalPriority = ApprovalPriority.NORMAL,
        timeout_seconds: float = 3600.0,
    ) -> ApprovalRequest:
        """Create an approval request."""
        req = ApprovalRequest(
            operation=operation,
            title=title,
            description=description,
            context=context,
            required_approvals=required_approvals,
            approvers=approvers or [],
            priority=priority,
            timeout_seconds=timeout_seconds,
        )
        self._queue.enqueue(req)
        return req

    def approve(
        self,
        approval_id: str,
        approver_id: str,
        comment: str = "",
    ) -> bool:
        """Approve a request."""
        with self._lock:
            req = self._queue.get(approval_id)
            if req is None or req.status != ApprovalStatus.PENDING:
                return False
            if approver_id not in req.approved_by:
                req.approved_by.append(approver_id)
            if comment:
                req.comments.append(f"[APPROVED by {approver_id}] {comment}")

            if len(req.approved_by) >= req.required_approvals:
                return self._queue.update_status(approval_id, ApprovalStatus.APPROVED)
        return True

    def reject(
        self,
        approval_id: str,
        rejecter_id: str,
        comment: str = "",
    ) -> bool:
        """Reject a request."""
        with self._lock:
            req = self._queue.get(approval_id)
            if req is None or req.status != ApprovalStatus.PENDING:
                return False
            if rejecter_id not in req.rejected_by:
                req.rejected_by.append(rejecter_id)
            if comment:
                req.comments.append(f"[REJECTED by {rejecter_id}] {comment}")
            return self._queue.update_status(approval_id, ApprovalStatus.REJECTED)

    def delegate(
        self,
        approval_id: str,
        from_id: str,
        to_id: str,
    ) -> bool:
        """Delegate an approval request to someone else."""
        with self._lock:
            req = self._queue.get(approval_id)
            if req is None or req.status != ApprovalStatus.PENDING:
                return False
            req.delegated_to = to_id
            req.comments.append(f"[DELEGATED] {from_id} → {to_id}")
            return self._queue.update_status(approval_id, ApprovalStatus.DELEGATED)

    def cancel(self, approval_id: str) -> bool:
        return self._queue.update_status(approval_id, ApprovalStatus.CANCELLED)

    def check_expired(self) -> int:
        """Check and expire stale requests."""
        return self._queue.expire_stale()

    # ── Query ────────────────────────────────────────────────

    def get(self, approval_id: str) -> Optional[ApprovalRequest]:
        return self._queue.get(approval_id)

    def get_pending(self) -> list[ApprovalRequest]:
        return self._queue.get_pending()

    def get_by_priority(self, priority: ApprovalPriority) -> list[ApprovalRequest]:
        return [r for r in self.get_pending() if r.priority == priority]

    def get_history(self) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._queue._history)

    def stats(self) -> dict:
        return self._queue.stats()
