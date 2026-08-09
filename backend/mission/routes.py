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

import asyncio
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
    build_mission_report,
)

logger = logging.getLogger("hermes_os.mission.routes")

router = APIRouter(prefix="/missions", tags=["missions"])

_executor: Optional[GraphExecutor] = None
_planner: Optional[Any] = None
_memory_manager: Optional[Any] = None
_evolution_engine: Optional[Any] = None
_aegis_engine: Optional[Any] = None
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


def set_evolution_engine(ee: Any) -> None:
    """Inject the Evolution Engine so a completed mission feeds real
    metrics into it (HOS-068) — before this, only AutonomousMemoryLoop did
    this for autonomous goals; a mission run through this router never
    reached it at all."""
    global _evolution_engine
    _evolution_engine = ee


def register_mission(mission: Mission) -> None:
    """Make a mission built elsewhere visible through this router's own
    list/get/graph/progress/report endpoints (HOS-068).

    AutonomousOrchestrator's real DAG path (HOS-067) builds a Mission via
    the same MissionPlanner this router uses, but that mission never
    reached this module's own ``_missions`` dict — the only thing
    ``create_mission()`` ever populated it. A mission started from
    Autonomous was therefore invisible to ``GET /missions`` even though it
    ran on the exact same GraphExecutor. One call from the orchestrator
    after ``build_mission()`` closes that gap without merging the two
    entry points into one.
    """
    _missions[mission.mission_id] = mission


def _get_aegis_engine() -> Any:
    """Lazy singleton, same construction as every other ad-hoc AegisEngine
    in this codebase (agents/aegis.py, model_intelligence/routes.py,
    autonomous_guard.py's wiring) — no shared bootstrap-level Aegis service
    exists yet to reuse instead."""
    global _aegis_engine
    if _aegis_engine is None:
        from backend.core.config import get_settings, load_security_config
        from backend.security.aegis_engine import AegisEngine
        from backend.security.permission_matrix import PermissionMatrix

        settings = get_settings()
        _aegis_engine = AegisEngine(
            PermissionMatrix(load_security_config()), settings.allowed_paths_list,
        )
    return _aegis_engine


def _check_mission_security(mission: Mission) -> Optional[dict[str, Any]]:
    """Risk-based Aegis gate before a mission may start (HOS-068) — mirrors
    AutonomousOrchestrator's own gate exactly. Before this,
    ``/missions/{id}/start`` had no security check of any kind.

    Only checked when the mission is bound to a real project
    (local_path/repository) — a plain mission with no real-world footprint
    proceeds exactly as it did before this existed, for the same reason
    Autonomous doesn't gate every goal: the individual risky actions a
    task's tools take (file writes, git, network) are already separately
    gated at the point of use, so blocking every mission by default would
    be friction with no matching risk.

    Returns None to let the caller proceed, or a response dict to return
    immediately instead (mission status is already updated either way).
    """
    if not (mission.context.local_path or mission.context.repository):
        return None

    from backend.security.aegis_engine import ActionRequest, Verdict

    engine = _get_aegis_engine()

    if mission.context.local_path:
        path_decision = engine.evaluate(ActionRequest(
            action_type="file_read",
            description=f"mission {mission.mission_id} local_path",
            target_path=mission.context.local_path,
        ))
        if path_decision.verdict != Verdict.ALLOW:
            mission.status = MissionStatus.FAILED
            return {
                "mission_id": mission.mission_id,
                "status": mission.status.value,
                "error": f"local_path denied by Aegis: {path_decision.reason}",
            }

    decision = engine.evaluate(ActionRequest(
        action_type="mission_execute",
        description=f"start mission {mission.mission_id}",
        target_path=mission.context.local_path or None,
    ))
    if decision.verdict == Verdict.DENY:
        mission.status = MissionStatus.FAILED
        return {
            "mission_id": mission.mission_id,
            "status": mission.status.value,
            "error": f"blocked by Aegis: {decision.reason}",
        }
    if decision.verdict == Verdict.REQUIRE_HUMAN_VALIDATION:
        # A real human-in-the-loop signal, not a fabricated pause. Resuming
        # doesn't re-check Aegis — a deliberate choice mirroring Autonomous:
        # once a human has acted (via /resume), that act *is* the approval.
        mission.status = MissionStatus.PAUSED
        return {
            "mission_id": mission.mission_id,
            "status": mission.status.value,
            "reason": decision.reason,
        }
    return None


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

    # HOS-068: beyond episodic memory, mirroring what AutonomousMemoryLoop
    # already does for autonomous goals — a mission run through this
    # router never fed either of these before.
    if mission.status == MissionStatus.COMPLETED:
        _record_procedure(mission)
    _feed_evolution_engine(mission)


def _record_procedure(mission: Mission) -> None:
    """Store the real sequence of completed task titles as a procedure —
    only called for a genuinely COMPLETED mission, so "derived_from" is
    honest: a strategy that worked, not one that was merely attempted."""
    if _memory_manager is None:
        return

    from backend.memory.memory_models import ProceduralMemory

    ordered = sorted(mission.nodes, key=lambda n: n.completed_at or mission.created_at)
    try:
        _memory_manager.store_procedure(ProceduralMemory(
            name=mission.title or mission.mission_id,
            description=mission.objective or mission.description,
            category="workflow",
            steps=[n.title for n in ordered if n.title],
            derived_from_missions=[mission.mission_id],
            success_rate=1.0,
            usage_count=1,
            tags=list(mission.context.tags) + [mission.type.value],
        ))
    except Exception:
        logger.warning(
            "procedural write-back failed for mission %s", mission.mission_id,
            exc_info=True,
        )


def _feed_evolution_engine(mission: Mission) -> None:
    """Real, measured metrics only — success/duration as they actually
    happened, the same signal AutonomousMemoryLoop already sends for
    goals."""
    if _evolution_engine is None:
        return

    from backend.evolution.evolution_models import SystemMetrics

    duration_s = 0.0
    if mission.started_at is not None and mission.completed_at is not None:
        duration_s = (mission.completed_at - mission.started_at).total_seconds()

    try:
        _evolution_engine.ingest_metrics(SystemMetrics(
            agent_success_rate=1.0 if mission.status == MissionStatus.COMPLETED else 0.5,
            agent_avg_duration_ms=duration_s * 1000.0,
            mission_avg_duration_s=duration_s,
        ))
    except Exception:
        logger.warning(
            "evolution engine feed failed for mission %s", mission.mission_id,
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
    # Project binding (HOS-068) — read here (not only threaded into
    # PlanningRequest via _plan_nodes) so it's still known after planning,
    # for _check_mission_security() and the report/detail views.
    mission.context.local_path = payload.get("local_path", "") or ""
    mission.context.repository = payload.get("repository", "") or ""
    mission.context.branch = payload.get("branch", "") or ""

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
                # True when the real decomposition failed and this mission
                # ran a generic, request-independent task template instead
                # — surfaced in the list too, not just the report, so it's
                # visible before opening a mission that turns out to be noise.
                "plan_is_generic": m.metadata.get("decomposition_method") == "generic_fallback",
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
        "local_path": mission.context.local_path,
        "repository": mission.context.repository,
        "branch": mission.context.branch,
        "created_at": mission.created_at.isoformat(),
        "decomposition_method": mission.metadata.get("decomposition_method", "llm"),
        "plan_is_generic": mission.metadata.get("decomposition_method") == "generic_fallback",
    }


@router.get("/{mission_id}/graph")
async def get_graph(mission_id: str):
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    return _executor.get_graph_data(mission)


async def _run_mission_steps(mission: Mission) -> int:
    """Drive execute_step() until terminal, paused, or no more ready nodes.

    Yields to the event loop between passes (HOS-068, ``await
    asyncio.sleep(0)``) so a concurrent ``/pause`` request can actually be
    processed mid-run. Before this, the whole walk ran inside one ``async
    def`` handler with no ``await`` point in the loop body — FastAPI's
    single event loop could not service *any* other request, including
    ``/pause``, until the mission finished or got stuck, which made
    ``/pause`` structurally unable to interrupt anything.
    """
    terminal = (MissionStatus.COMPLETED, MissionStatus.FAILED,
                MissionStatus.CANCELLED)
    executed = 0
    passes = 0
    while (mission.status not in terminal
           and mission.status != MissionStatus.PAUSED
           and passes < MAX_EXECUTION_PASSES):
        stepped = _executor.execute_step(mission)
        passes += 1
        if stepped == 0:
            # No node was ready: either the graph is finished or it is blocked.
            break
        executed += stepped
        await asyncio.sleep(0)

    if passes >= MAX_EXECUTION_PASSES:
        logger.warning("mission %s hit the %d-pass ceiling", mission.mission_id,
                       MAX_EXECUTION_PASSES)

    if mission.status in terminal:
        _record_episode(mission)

    return executed


@router.post("/{mission_id}/start")
async def start_mission(mission_id: str):
    """Start the mission and walk its DAG through the shared execution engine.

    ``start_mission()`` only marks the mission running and announces the root
    nodes; the work happens in ``execute_step()``, which no caller ever invoked.
    """
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}

    security_response = _check_mission_security(mission)
    if security_response is not None:
        return security_response

    ok = _executor.start_mission(mission)
    if not ok:
        return {"error": f"Cannot start mission in status {mission.status.value}"}

    executed = await _run_mission_steps(mission)

    return {
        "mission_id": mission_id,
        "status": mission.status.value,
        "nodes_executed": executed,
        "progress": _executor.get_progress(mission),
    }


@router.post("/{mission_id}/pause")
async def pause_mission(mission_id: str):
    """Pause a running mission (HOS-068).

    Genuinely interruptible, not cosmetic: a concurrent ``/start`` call's
    stepping loop checks ``mission.status`` between every pass (see
    ``_run_mission_steps``), so setting it here actually stops the walk
    before its next step — not merely a status label a background process
    ignores.
    """
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}
    if mission.status != MissionStatus.RUNNING:
        return {"error": f"Cannot pause mission in status {mission.status.value}"}
    mission.status = MissionStatus.PAUSED
    return {"mission_id": mission_id, "status": mission.status.value}


@router.post("/{mission_id}/resume")
async def resume_mission(mission_id: str):
    """Resume a paused mission — actually continues the DAG walk (unlike
    Autonomous's current pause/resume, which only flips the status flag;
    see AutonomousOrchestrator.resume_goal()'s own note on that gap) since
    the mission's DAG state (which nodes are done/ready) lives on the
    Mission/MissionNode objects themselves, not in a stack frame that was
    already unwound."""
    mission = _missions.get(mission_id)
    if mission is None or _executor is None:
        return {"error": "Mission or executor not found"}
    if mission.status != MissionStatus.PAUSED:
        return {"error": f"Cannot resume mission in status {mission.status.value}"}
    mission.status = MissionStatus.RUNNING
    if mission.started_at is None:
        # A mission the Aegis gate paused (_check_mission_security) never
        # reached _executor.start_mission() — the only other place that
        # sets this — so without it build_mission_report() reports
        # total_duration_ms: 0.0 even after a resumed mission genuinely ran.
        from datetime import datetime, timezone

        mission.started_at = datetime.now(timezone.utc)

    executed = await _run_mission_steps(mission)

    return {
        "mission_id": mission_id,
        "status": mission.status.value,
        "nodes_executed": executed,
        "progress": _executor.get_progress(mission),
    }


@router.get("/{mission_id}/report")
async def get_report(mission_id: str):
    """Final mission report (HOS-068) — derived from the mission's own
    real, already-measured state; see build_mission_report()."""
    mission = _missions.get(mission_id)
    if mission is None:
        return {"error": "Mission not found"}
    return build_mission_report(mission).to_dict()


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
