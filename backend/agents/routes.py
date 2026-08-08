"""FastAPI routes for the Agent Supervisor (HOS-043)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body

from backend.agents.agent_models import AgentCapability
from backend.agents.agent_supervisor import AgentSupervisor

router = APIRouter(prefix="/agents", tags=["agents"])

_supervisor: Optional[AgentSupervisor] = None
_trust_engine: Optional[Any] = None


def create_agent_routes(supervisor: AgentSupervisor) -> APIRouter:
    global _supervisor
    _supervisor = supervisor
    return router


def set_trust_engine(trust_engine: Any) -> None:
    """Inject the real AgentTrustEngine (HOS-070) so the Cockpit's Agent
    Center can show a trust score fed by real task outcomes instead of a
    permanently-fresh default score."""
    global _trust_engine
    _trust_engine = trust_engine


def _ensure_supervisor():
    if _supervisor is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Agent supervisor not initialized")


def _trust_fields(agent_name: str) -> dict:
    """Real trust score/level for an agent, or a clearly-labelled absence
    rather than a fabricated number when no trust engine is wired."""
    if _trust_engine is None:
        return {"trust_score": None, "trust_level": None}
    try:
        score = _trust_engine.get_score(agent_name)
        return {"trust_score": score.score, "trust_level": score.level.value}
    except Exception:
        return {"trust_score": None, "trust_level": None}


# ── Agent CRUD ───────────────────────────────────────────────

@router.get("")
async def list_agents():
    """List all agents."""
    _ensure_supervisor()
    agents = _supervisor.list_agents()
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "status": a.status.value,
                "capabilities": [c.value for c in a.capabilities],
                "preferred_runtime": a.preferred_runtime,
                "preferred_model": a.preferred_model,
                "success_rate": a.success_rate,
                "total_tasks": a.total_tasks,
                # HOS-070: were only on the /{agent_id} detail response —
                # the Cockpit's list view reads the row it already has
                # rather than re-fetching detail per selection, so a
                # successful agent's own list row showed "0 ok, 0 failed"
                # even at 100% success (found via manual browser
                # verification: a dispatched agent's list row and its
                # success_rate visibly disagreed).
                "successful_tasks": a.successful_tasks,
                "failed_tasks": a.failed_tasks,
                "current_task_id": a.current_task_id,
                "current_mission_id": a.current_mission_id,
                **_trust_fields(a.name),
            }
            for a in agents
        ],
        "total": len(agents),
    }


@router.get("/status")
async def get_agent_status():
    """Get agent statistics."""
    _ensure_supervisor()
    return _supervisor.get_stats()


@router.get("/metrics")
async def get_all_metrics():
    """Get metrics for all agents."""
    _ensure_supervisor()
    metrics = _supervisor.get_all_metrics()
    return {
        "metrics": [
            {
                "agent_id": m.agent_id,
                "total_tasks": m.total_tasks,
                "successful_tasks": m.successful_tasks,
                "failed_tasks": m.failed_tasks,
                "success_rate": m.success_rate,
                "avg_duration_ms": round(m.avg_duration_ms, 1),
                "current_load": m.current_load,
            }
            for m in metrics
        ]
    }


@router.post("")
async def create_agent(payload: dict = Body(...)):
    """Create a new agent."""
    _ensure_supervisor()
    caps = []
    for c in payload.get("capabilities", []):
        try:
            caps.append(AgentCapability(c))
        except ValueError:
            pass

    agent = _supervisor.create_agent(
        name=payload.get("name", "Agent"),
        capabilities=caps,
        preferred_runtime=payload.get("preferred_runtime", ""),
        preferred_model=payload.get("preferred_model", ""),
        description=payload.get("description", ""),
    )
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "status": agent.status.value,
        "capabilities": [c.value for c in agent.capabilities],
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent details."""
    _ensure_supervisor()
    agent = _supervisor.get_agent(agent_id)
    if agent is None:
        return {"error": "Agent not found"}
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "status": agent.status.value,
        "capabilities": [c.value for c in agent.capabilities],
        "preferred_runtime": agent.preferred_runtime,
        "preferred_model": agent.preferred_model,
        "success_rate": agent.success_rate,
        "total_tasks": agent.total_tasks,
        "successful_tasks": agent.successful_tasks,
        "failed_tasks": agent.failed_tasks,
        "current_mission_id": agent.current_mission_id,
        "current_task_id": agent.current_task_id,
        "created_at": agent.created_at.isoformat(),
        "last_active_at": agent.last_active_at.isoformat() if agent.last_active_at else None,
        "history": _supervisor.get_agent_history(agent_id),
        "tasks": _supervisor.get_agent_tasks(agent_id),
        **_trust_fields(agent.name),
    }


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str):
    """Start (resume) an agent."""
    _ensure_supervisor()
    ok = _supervisor.resume_agent(agent_id)
    return {"agent_id": agent_id, "ok": ok}


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop an agent."""
    _ensure_supervisor()
    ok = _supervisor.stop_agent(agent_id)
    return {"agent_id": agent_id, "ok": ok}


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str):
    """Pause an agent."""
    _ensure_supervisor()
    ok = _supervisor.pause_agent(agent_id)
    return {"agent_id": agent_id, "ok": ok}
