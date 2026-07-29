"""Security Routes for Hermes OS (HOS-057).

REST API endpoints for security management.
"""

from __future__ import annotations

from typing import Any

from .security_engine import SecurityEngine
from .security_models import ResourceType, ThreatLevel, TrustLevel

# Global engine instance (singleton pattern)
_engine: SecurityEngine | None = None


def get_engine() -> SecurityEngine:
    global _engine
    if _engine is None:
        _engine = SecurityEngine()
    return _engine


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
