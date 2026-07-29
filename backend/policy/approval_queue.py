"""Approval Queue for HOS-046.

Thread-safe priority queue for human approval requests.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.policy.policy_models import (
    ApprovalPriority,
    ApprovalRequest,
    ApprovalStatus,
)


class ApprovalQueue:
    """Thread-safe priority queue for approval requests.

    Sorted by priority (CRITICAL first) then creation time (oldest first).
    """

    _PRIORITY_ORDER: dict[ApprovalPriority, int] = {
        ApprovalPriority.CRITICAL: 3,
        ApprovalPriority.HIGH: 2,
        ApprovalPriority.NORMAL: 1,
        ApprovalPriority.LOW: 0,
    }

    def __init__(self, on_event: Optional[Callable] = None) -> None:
        self._lock = threading.RLock()
        self._on_event = on_event
        self._requests: dict[str, ApprovalRequest] = {}
        self._by_status: dict[ApprovalStatus, list[str]] = {
            s: [] for s in ApprovalStatus
        }
        self._history: list[ApprovalRequest] = []

    def enqueue(self, request: ApprovalRequest) -> None:
        """Add a request to the queue."""
        with self._lock:
            if request.expires_at is None:
                request.expires_at = datetime.now(timezone.utc)
                from datetime import timedelta
                request.expires_at += timedelta(seconds=request.timeout_seconds)
            self._requests[request.approval_id] = request
            self._by_status[request.status].append(request.approval_id)

        if self._on_event:
            self._on_event("approval.requested", {
                "approval_id": request.approval_id,
                "operation": request.operation,
                "priority": request.priority.value,
            }, severity="info")

    def dequeue(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Remove a request from the queue."""
        with self._lock:
            req = self._requests.pop(approval_id, None)
            if req:
                lst = self._by_status.get(req.status, [])
                if approval_id in lst:
                    lst.remove(approval_id)
                self._history.append(req)
            return req

    def get_pending(self) -> list[ApprovalRequest]:
        """Get pending requests sorted by priority (highest first)."""
        with self._lock:
            ids = list(self._by_status.get(ApprovalStatus.PENDING, []))
            pending = [self._requests[aid] for aid in ids if aid in self._requests]
            # Sort: highest priority first, then oldest first
            pending.sort(key=lambda r: (
                -self._PRIORITY_ORDER.get(r.priority, 0),
                r.created_at,
            ))
            return pending

    def get(self, approval_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(approval_id)

    def update_status(
        self, approval_id: str, new_status: ApprovalStatus
    ) -> bool:
        """Update status and maintain indexes."""
        with self._lock:
            req = self._requests.get(approval_id)
            if req is None:
                return False
            old = req.status
            req.status = new_status
            if approval_id in self._by_status.get(old, []):
                self._by_status[old].remove(approval_id)
            self._by_status[new_status].append(approval_id)

            if new_status in (
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
                ApprovalStatus.EXPIRED,
                ApprovalStatus.CANCELLED,
            ):
                req.resolved_at = datetime.now(timezone.utc)

            if new_status == ApprovalStatus.APPROVED and self._on_event:
                self._on_event("approval.granted", {
                    "approval_id": approval_id,
                    "operation": req.operation,
                }, severity="info")
            elif new_status == ApprovalStatus.REJECTED and self._on_event:
                self._on_event("approval.rejected", {
                    "approval_id": approval_id,
                    "operation": req.operation,
                }, severity="info")
        return True

    def expire_stale(self) -> int:
        """Expire requests past their timeout. Returns count expired."""
        count = 0
        with self._lock:
            for req in list(self._requests.values()):
                if req.is_expired and req.status == ApprovalStatus.PENDING:
                    self.update_status(req.approval_id, ApprovalStatus.EXPIRED)
                    count += 1
                    if self._on_event:
                        self._on_event("approval.expired", {
                            "approval_id": req.approval_id,
                        }, severity="warning")
        return count

    def count_by_status(self, status: ApprovalStatus) -> int:
        with self._lock:
            return len([aid for aid in self._by_status.get(status, [])
                       if aid in self._requests])

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": len(self._requests),
                "by_status": {
                    s.value: self.count_by_status(s) for s in ApprovalStatus
                },
                "by_priority": {
                    p.value: sum(1 for r in self._requests.values() if r.priority == p)
                    for p in ApprovalPriority
                },
                "history_length": len(self._history),
            }
