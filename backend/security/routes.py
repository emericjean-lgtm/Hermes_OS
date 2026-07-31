"""Security Routes for Hermes OS (HOS-057).

REST API endpoints for security management.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from .security_engine import SecurityEngine
from .security_models import ResourceType, ThreatLevel

# Global engine instance (singleton pattern)
_engine: SecurityEngine | None = None


def get_engine() -> SecurityEngine:
    global _engine
    if _engine is None:
        _engine = SecurityEngine()
    return _engine


def create_security_routes(engine: SecurityEngine) -> APIRouter:
    """Bind the container-owned engine to these routes (HOS-066B).

    Seeds the module singleton so ``get_engine()`` and the HTTP layer share one
    instance — without this, the lazy fallback above would build a *second*
    engine with no ``on_event``, and its events would go nowhere.
    """
    global _engine
    _engine = engine
    return router


# ── API Handler Functions ────────────────────────────────────

def handle_get_status() -> dict[str, Any]:
    """GET /security/status"""
    engine = get_engine()
    return engine.get_status()


def handle_get_policies() -> list[dict]:
    """GET /security/policies"""
    engine = get_engine()
    return [p.to_dict() for p in engine.permissions.get_policies()]


def handle_check_access(data: dict) -> dict[str, Any]:
    """POST /security/check"""
    engine = get_engine()
    rt = ResourceType(data.get("resource_type", "agent"))
    return engine.check_access(
        principal_id=data["principal_id"],
        resource_type=rt,
        resource_id=data["resource_id"],
        operation=data.get("operation", "access"),
        context=data.get("context"),
    )


def handle_get_events(limit: int = 100) -> list[dict]:
    """GET /security/events"""
    engine = get_engine()
    return engine.permissions.get_history(limit=limit)


def handle_get_trust(agent_id: str) -> dict:
    """GET /security/trust/{agent_id}"""
    engine = get_engine()
    score = engine.trust.get_score(agent_id)
    return score.to_dict()


def handle_grant_permission(data: dict) -> dict:
    """POST /security/permissions/grant"""
    engine = get_engine()
    perm = engine.permissions.grant_permission(
        principal_id=data["principal_id"],
        resource_type=ResourceType(data.get("resource_type", "agent")),
        resource_id=data["resource_id"],
        allowed=data.get("allowed", True),
        granted_by=data.get("granted_by", "system"),
    )
    return perm.to_dict()


def handle_revoke_permission(data: dict) -> dict:
    """POST /security/permissions/revoke"""
    engine = get_engine()
    success = engine.permissions.revoke_permission(
        principal_id=data["principal_id"],
        resource_type=ResourceType(data.get("resource_type", "agent")),
        resource_id=data["resource_id"],
    )
    return {"success": success}


def handle_get_threats(level: str | None = None, limit: int = 50) -> list[dict]:
    """GET /security/threats"""
    engine = get_engine()
    tl = ThreatLevel(level) if level else None
    return [t.to_dict() for t in engine.threats.get_threats(level=tl, limit=limit)]


def handle_mitigate_threat(data: dict) -> dict:
    """POST /security/threats/mitigate"""
    engine = get_engine()
    ok = engine.threats.mitigate_threat(
        data["threat_id"], data.get("action", "auto_mitigate")
    )
    return {"success": ok}


# ── HTTP surface ─────────────────────────────────────────────
#
# Thin delegation to the handlers above: the paths and methods are exactly
# those declared in SECURITY_ROUTES below, which was the module's intended
# contract but had no APIRouter to make it reachable.

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/status")
async def get_status() -> dict[str, Any]:
    return handle_get_status()


@router.get("/policies")
async def get_policies() -> list[dict]:
    return handle_get_policies()


@router.post("/check")
async def check_access(payload: dict = Body(...)) -> dict[str, Any]:
    return handle_check_access(payload)


@router.get("/events")
async def get_events(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    return handle_get_events(limit)


@router.get("/trust/{agent_id}")
async def get_trust(agent_id: str) -> dict:
    return handle_get_trust(agent_id)


@router.post("/permissions/grant")
async def grant_permission(payload: dict = Body(...)) -> dict:
    return handle_grant_permission(payload)


@router.post("/permissions/revoke")
async def revoke_permission(payload: dict = Body(...)) -> dict:
    return handle_revoke_permission(payload)


@router.get("/threats")
async def get_threats(
    level: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return handle_get_threats(level, limit)


@router.post("/threats/mitigate")
async def mitigate_threat(payload: dict = Body(...)) -> dict:
    return handle_mitigate_threat(payload)


# ── API endpoint list for integration ────────────────────────

SECURITY_ROUTES = [
    {"path": "/security/status", "method": "GET", "handler": handle_get_status},
    {"path": "/security/policies", "method": "GET", "handler": handle_get_policies},
    {"path": "/security/check", "method": "POST", "handler": handle_check_access},
    {"path": "/security/events", "method": "GET", "handler": handle_get_events},
    {"path": "/security/trust/{agent_id}", "method": "GET", "handler": handle_get_trust},
    {"path": "/security/permissions/grant", "method": "POST", "handler": handle_grant_permission},
    {"path": "/security/permissions/revoke", "method": "POST", "handler": handle_revoke_permission},
    {"path": "/security/threats", "method": "GET", "handler": handle_get_threats},
    {"path": "/security/threats/mitigate", "method": "POST", "handler": handle_mitigate_threat},
]
