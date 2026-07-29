"""FastAPI routes for the Runtime Recovery Engine (HOS-036)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from backend.runtime.recovery.recovery_engine import RecoveryEngine

router = APIRouter(prefix="/runtime/recovery", tags=["runtime-recovery"])

_engine: Optional[RecoveryEngine] = None


def create_recovery_routes(engine: RecoveryEngine) -> APIRouter:
    """Factory: bind a RecoveryEngine to the routes."""
    global _engine
    _engine = engine
    return router


@router.get("/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    """Get recovery attempt history."""
    if _engine is None:
        return {"attempts": [], "total": 0}

    attempts = _engine.get_history(limit)
    return {
        "attempts": [
            {
                "attempt_id": a.attempt_id,
                "incident_id": a.incident_id,
                "status": a.status.value,
                "actions_count": len(a.actions),
                "results": [
                    {
                        "action_type": r.action_type.value,
                        "success": r.success,
                        "message": r.message,
                        "duration_ms": r.duration_ms,
                    }
                    for r in a.results
                ],
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
                "errors": a.errors,
            }
            for a in attempts
        ],
        "total": len(attempts),
    }


@router.get("/status")
async def get_status():
    """Get recovery engine status."""
    if _engine is None:
        return {"error": "RecoveryEngine not initialised"}
    return _engine.get_status()


@router.post("/{incident_id}/retry")
async def retry_incident(incident_id: str):
    """Retry recovery for a failed incident."""
    if _engine is None:
        return {"error": "RecoveryEngine not initialised"}

    attempt = _engine.retry_incident(incident_id)
    if attempt is None:
        return {"success": False, "reason": "Incident not found or no policies match"}

    return {
        "success": attempt.status.value in ("completed", "in_progress"),
        "attempt_id": attempt.attempt_id,
        "status": attempt.status.value,
        "actions_executed": len(attempt.results),
    }
