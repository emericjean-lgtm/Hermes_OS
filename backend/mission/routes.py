"""FastAPI routes for the Mission Graph Engine (HOS-041).

This surface used to be a DAG container and nothing more: it required the caller
to supply ``nodes`` and ``edges``, never asked the Mission Planner to decompose a
described goal, and ``/start`` only flipped the status label to ``running``
because nothing ever drove ``GraphExecutor.execute_step()``. A mission created
here reported ``nodes: 0`` and stayed at 0% forever, silently, while
``/api/v1/autonomous`` executed for real.

Both surfaces now run the same pipeline (R-002 P1): the planner produces the DAG,
and the graph executor walks it with its ``execute_node`` hook bound to the
shared ``MissionExecutor``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body

from backend.mission.graph_executor import GraphExecutor
from backend.mission.mission_models import (
    Mission,
    MissionEdge,
    MissionNode,
    MissionPriority,
    MissionStatus,
    MissionType,
)

logger = logging.getLogger("hermes_os.mission.routes")

router = APIRouter(prefix="/missions", tags=["missions"])

_executor: Optional[GraphExecutor] = None
_planner: Optional[Any] = None
_memory_manager: Optional[Any] = None
_missions: dict[str, Mission] = {}

#: Safety valve on the DAG walk. execute_step() runs every currently-ready node,
#: so a well-formed graph needs at most one pass per dependency level; this bounds
#: a graph that somehow never reaches a terminal state.
MAX_EXECUTION_PASSES = 100


def create_mission_routes(executor: GraphExecutor) -> APIRouter:
    global _executor
    _executor = executor
    return router


def set_mission_planner(planner: Any) -> None:
    """Inject the Mission Planner.

    Called from the planner's own route binder rather than this one: binders run
    inline as each service is built, and the planner is built after the graph
    executor it depends on, so pulling it in from here would both fail and create
    a dependency cycle.
    """
    global _planner
    _planner = planner


def set_memory_manager(mm: Any) -> None:
    """Inject the memory manager so terminal missions write an episode.

    Same injection pattern as set_mission_planner(), for the same reason:
    /autonomous fed episodic memory from mission one (AutonomousMemoryLoop)
    while /missions never did, so a mission run through this router left
    episodic.total unmoved no matter how many missions completed here —
    both surfaces share one execution engine since R-002 P1, but recording
    the outcome was never wired for this one."""
    global _memory_manager
    _memory_manager = mm


def _record_episode(mission: Mission) -> None:
    """Best-effort write-back once a mission reaches a terminal status.

    Mirrors AutonomousMemoryLoop.process_report()'s episodic write: never
    raises past this point, since a learning write must not fail (or
    retroactively un-complete) a mission that already finished."""
    if _memory_manager is None:
        return

    from backend.memory.memory_models import EpisodicMemory

    duration = 0.0
    if mission.started_at is not None and mission.completed_at is not None:
        duration = (mission.completed_at - mission.started_at).total_seconds()

    agents_used = sorted({n.preferred_agent for n in mission.nodes if n.preferred_agent})
    runtimes_used = sorted({n.preferred_runtime for n in mission.nodes if n.preferred_runtime})

    try:
        _memory_manager.record_episode(EpisodicMemory(
            mission_id=mission.mission_id,
            mission_title=mission.title,
            mission_type=mission.type.value,
            success=mission.status == MissionStatus.COMPLETED,
            total_nodes=mission.total_nodes(),
            completed_nodes=mission.completed_nodes(),
            failed_nodes=mission.failed_nodes(),
            duration_seconds=duration,
            agents_used=agents_used,
            runtimes_used=runtimes_used,
            tags=list(mission.context.tags),
        ))
    except Exception:
        logger.warning(
            "episodic write-back failed for mission %s", mission.mission_id,
            exc_info=True,
        )


def _plan_nodes(mission: Mission, payload: dict) -> tuple[list[MissionNode], list[MissionEdge]]:
    """Decompose the mission's description into a DAG via the Mission Planner.

    Only used when the caller supplied no explicit graph. Returns empty lists if
    no planner is wired or planning yields nothing, so the caller can report the
    situation instead of pretending a graph exists.
    """
    if _planner is None:
        logger.warning("no mission planner wired; mission %s has no graph",
                       mission.mission_id)
        return [], []

    from backend.mission.planner.planner_models import PlanningRequest

    request = PlanningRequest(
        user_request=mission.description or mission.title,
        objective=mission.objective or mission.title,
        context=payload.get("context", {}) or {},
        repository=payload.get("repository", "") or "",
        branch=payload.get("branch", "") or "",
        specification=payload.get("specification", "") or "",
        preferred_runtime=payload.get("preferred_runtime", "") or "",
        tags=list(payload.get("tags", []) or []),
    )

    try:
        result = _planner.plan(request)
        planned = _planner.build_mission(
            result, title=mission.title, objective=mission.objective)
    except Exception:
        logger.warning("planning failed for mission %s",
                       mission.mission_id, exc_info=True)
        return [], []

    return list(planned.nodes), list(planned.edges)


@router.post("")
async def create_mission(payload: dict = Body(...)):
    """Create a mission, decomposing its description into a DAG when needed."""
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

    # An explicit graph wins; otherwise the planner decomposes the goal. This is
    # the step that used to be missing entirely.
    planned = False
    if not nodes:
        nodes, edges = _plan_nodes(mission, payload)
        planned = bool(nodes)

    issues: list[str] = []
    if _executor:
        issues = _executor.build_graph(mission, nodes, edges) or []

    _missions[mission.mission_id] = mission

    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "status": mission.status.value,
        "nodes": mission.total_nodes(),
        "edges": len(mission.edges),
        "planned": planned,
        "validation_issues": issues,
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
    """Start the mission and walk its DAG through the shared execution engine.

    ``start_mission()`` only marks the mission running and announces the root
    nodes; the work happens in ``execute_step()``, which no caller ever invoked.
    """
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    ok = _executor.start_mission(mission)
    if not ok:
        return {"error": f"Cannot start mission in status {mission.status.value}"}

    terminal = (MissionStatus.COMPLETED, MissionStatus.FAILED,
                MissionStatus.CANCELLED)
    executed = 0
    passes = 0
    while mission.status not in terminal and passes < MAX_EXECUTION_PASSES:
        stepped = _executor.execute_step(mission)
        passes += 1
        if stepped == 0:
            # No node was ready: either the graph is finished or it is blocked.
            break
        executed += stepped

    if passes >= MAX_EXECUTION_PASSES:
        logger.warning("mission %s hit the %d-pass ceiling", mission_id,
                       MAX_EXECUTION_PASSES)

    if mission.status in terminal:
        _record_episode(mission)

    return {
        "mission_id": mission_id,
        "status": mission.status.value,
        "nodes_executed": executed,
        "progress": _executor.get_progress(mission),
    }


@router.post("/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    _executor.cancel_mission(mission)
    if mission.status == MissionStatus.CANCELLED:
        _record_episode(mission)
    return {"mission_id": mission_id, "status": mission.status.value}


@router.get("/{mission_id}/progress")
async def get_progress(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_progress(mission)
