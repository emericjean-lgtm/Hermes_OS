"""FastAPI routes for the Mission Graph Engine (HOS-041)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Query

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionType,
)

router = APIRouter(prefix="/missions", tags=["missions"])

_executor: Optional[GraphExecutor] = None
_missions: dict[str, Mission] = {}


def create_mission_routes(executor: GraphExecutor) -> APIRouter:
    global _executor
    _executor = executor
    return router


@router.post("")
async def create_mission(payload: dict = Body(...)):
    """Create a new mission."""
    mission = Mission(
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        objective=payload.get("objective", ""),
        type=MissionType(payload.get("type", "custom")),
        priority=MissionPriority(payload.get("priority", "normal")),
    )

    nodes_data = payload.get("nodes", [])
    nodes = [
        MissionNode(
            title=n.get("title", ""),
            description=n.get("description", ""),
            type=n.get("type", "task"),
            depends_on=n.get("depends_on", []),
            preferred_runtime=n.get("preferred_runtime", ""),
            required_skills=n.get("required_skills", []),
        )
        for n in nodes_data
    ]

    edges_data = payload.get("edges", [])
    edges = [
        MissionEdge(source_id=e["source_id"], target_id=e["target_id"])
        for e in edges_data
    ]

    if _executor:
        _executor.build_graph(mission, nodes, edges)

    _missions[mission.mission_id] = mission

    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
    }


@router.get("")
async def list_missions():
    return {
        "missions": [
            {
                "mission_id": m.mission_id,
                "title": m.title,
                "status": m.status.value,
                "progress": m.progress_pct(),
                "nodes": m.total_nodes(),
            }
            for m in _missions.values()
        ],
        "total": len(_missions),
    }


@router.get("/{mission_id}")
async def get_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}

    progress = _executor.get_progress(mission) if _executor else {}
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "description": mission.description,
        "objective": mission.objective,
        "type": mission.type.value,
        "priority": mission.priority.value,
        "status": mission.status.value,
        "progress": progress,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
        "created_at": mission.created_at.isoformat(),
    }


@router.get("/{mission_id}/graph")
async def get_graph(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_graph_data(mission)


@router.post("/{mission_id}/start")
async def start_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    ok = _executor.start_mission(mission)
    if not ok:
        return {"error": f"Cannot start mission in status {mission.status.value}"}

    return {"mission_id": mission_id, "status": mission.status.value}


@router.post("/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    _executor.cancel_mission(mission)
    return {"mission_id": mission_id, "status": mission.status.value}


@router.get("/{mission_id}/progress")
async def get_progress(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_progress(mission)
