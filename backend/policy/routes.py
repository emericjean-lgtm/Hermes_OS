"""FastAPI routes for the Policy Engine (HOS-046)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from backend.policy.policy_engine import PolicyEngine

router = APIRouter(prefix="/policy", tags=["policy"])

_engine: Optional[PolicyEngine] = None


def create_policy_routes(engine: PolicyEngine) -> APIRouter:
    global _engine
    _engine = engine
    return router


def _ensure_engine():
    if _engine is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Policy engine not initialized")


# ── Rules ────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules():
    _ensure_engine()
    return {"rules": _engine.get_rules()}


# ── Evaluate ─────────────────────────────────────────────────

@router.post("/evaluate")
async def evaluate(payload: dict = Body(...)):
    _ensure_engine()
    result = _engine.evaluate(
        operation=payload["operation"],
        agent_id=payload.get("agent_id", ""),
        user_id=payload.get("user_id", ""),
        mission_id=payload.get("mission_id", ""),
        node_id=payload.get("node_id", ""),
        workspace_id=payload.get("workspace_id", ""),
        risk_level=payload.get("risk_level", 0.0),
        details=payload.get("details"),
    )
    return {
        "result_id": result.result_id,
        "decision": result.decision.value,
        "matched_rules": result.matched_rules,
        "reasons": result.reasons,
        "requires_approval": result.requires_approval,
        "approval_id": result.approval_id,
    }


# ── Approvals ────────────────────────────────────────────────

approval_router = APIRouter(prefix="/approval", tags=["approval"])


@approval_router.get("")
async def list_approvals():
    _ensure_engine()
    pending = _engine.get_pending_approvals()
    return {
        "approvals": [
            {"id": a.approval_id, "operation": a.operation,
             "status": a.status.value, "priority": a.priority.value,
             "title": a.title}
            for a in pending
        ],
        "total": len(pending),
    }


@approval_router.post("/{approval_id}/approve")
async def approve(approval_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.approve(
        approval_id,
        payload.get("approver_id", ""),
        payload.get("comment", ""),
    )
    return {"ok": ok}


@approval_router.post("/{approval_id}/reject")
async def reject(approval_id: str, payload: dict = Body(...)):
    _ensure_engine()
    ok = _engine.reject(
        approval_id,
        payload.get("rejecter_id", ""),
        payload.get("comment", ""),
    )
    return {"ok": ok}


# ── Audit ────────────────────────────────────────────────────

audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("")
async def audit_log(
    agent_id: str = "",
    mission_id: str = "",
    operation: str = "",
    limit: int = 50,
):
    _ensure_engine()
    entries = _engine.get_audit_log(
        agent_id=agent_id,
        mission_id=mission_id,
        operation=operation,
        limit=limit,
    )
    return {
        "entries": [
            {"id": e.audit_id, "action": e.action.value,
             "agent": e.agent_id, "operation": e.operation,
             "decision": e.decision, "reason": e.reason,
             "created_at": e.created_at.isoformat()}
            for e in entries
        ],
        "total": len(entries),
    }
