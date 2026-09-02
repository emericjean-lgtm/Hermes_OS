"""HOS-028 route handlers — all endpoints delegate to MissionControlService.

Every function in this module receives the service instance through
FastAPI dependency injection and validates/transforms the HTTP request
before calling the service layer.

No business logic lives here — only HTTP→service mapping and response
serialisation.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse

from backend.services.mission_control import (
    MissionControlError,
    MissionControlService,
)

from .models import (
    ExecutionStartRequest,
    HermesConnectRequest,
    HermesTaskRequest,
    MemoryStoreRequest,
    MissionCreateRequest,
    SkillSelectRequest,
)


# ======================================================================
# Dependency — get the service instance from app state
# ======================================================================


def _get_service(request: Request) -> MissionControlService:
    """Retrieve the MissionControlService from FastAPI app state.

    The service must be injected at startup via ``app.state.mission_control = ...``.
    """
    svc = getattr(request.app.state, "mission_control", None)
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="MissionControlService not initialised.",
        )
    return svc


def _require_service(request: Request) -> MissionControlService:
    """Like :func:`_get_service` but raises 503 immediately if unavailable."""
    svc = _get_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Service unavailable.")
    return svc


# ======================================================================
# Helpers
# ======================================================================


def _mission_to_response(mission: Any) -> dict[str, Any]:
    """Convert a :class:`MissionInstance` to a response dict."""
    return {
        "mission_id": mission.context.mission_id,
        "title": mission.context.title,
        "objective": mission.context.objective,
        "state": mission.state.value if hasattr(mission.state, "value") else str(mission.state),
        "priority": mission.context.priority,
        "task_count": len(mission.task_plan.tasks) if mission.task_plan else 0,
        "agent_ids": list(mission.agents) if mission.agents else [],
        "metadata": dict(mission.metadata) if mission.metadata else {},
    }


def _memory_entry_to_response(entry: Any) -> dict[str, Any]:
    """Convert a :class:`MemoryEntry` to a response dict."""
    return {
        "id": entry.id,
        "scope": entry.scope.value if hasattr(entry.scope, "value") else str(entry.scope),
        "title": entry.title,
        "content": entry.content,
        "tags": sorted(entry.tags) if entry.tags else [],
        "importance": entry.importance,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def _skill_to_response(skill: Any) -> dict[str, Any]:
    """Convert a :class:`SkillDescriptor` to a response dict."""
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "capabilities": sorted(skill.capabilities) if skill.capabilities else [],
        "tags": sorted(skill.tags) if skill.tags else [],
        "priority": skill.priority,
        "estimated_tokens": skill.estimated_tokens,
    }


# ======================================================================
# MISSION HANDLERS
# ======================================================================


async def list_missions(
    request: Request,
    state: Optional[str] = Query(None, description="Filter by mission state"),
) -> JSONResponse:
    svc = _get_service(request)
    from backend.agent.supervisor import MissionState
    filter_state = MissionState(state) if state else None
    missions = svc.list_missions(state=filter_state)
    return JSONResponse({
        "missions": [_mission_to_response(m) for m in missions],
        "total": len(missions),
    })


async def create_mission(
    request: Request,
    body: MissionCreateRequest,
) -> JSONResponse:
    svc = _get_service(request)
    tasks = []
    for t in body.tasks:
        from backend.agent.task_planner import PlannedTask
        tasks.append(PlannedTask(
            id=t.get("id", f"task_{time.time_ns()}"),
            title=t.get("title", "task"),
            description=t.get("description", ""),
            runtime_capability=t.get("runtime_capability", "chat"),
            dependencies=frozenset(t.get("dependencies", [])),
            estimated_complexity=t.get("estimated_complexity", 1.0),
            parallelizable=t.get("parallelizable", True),
        ))
    try:
        mission = svc.create_mission(
            title=body.title,
            objective=body.objective,
            tasks=tasks,
            mission_id=body.mission_id,
            priority=body.priority,
        )
        return JSONResponse(_mission_to_response(mission), status_code=201)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def get_mission(
    request: Request,
    mission_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        mission = svc.get_mission(mission_id)
        return JSONResponse(_mission_to_response(mission))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def start_mission(
    request: Request,
    mission_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        mission = svc.start_mission(mission_id)
        return JSONResponse(_mission_to_response(mission))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def pause_mission(
    request: Request,
    mission_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        mission = svc.pause_mission(mission_id)
        return JSONResponse(_mission_to_response(mission))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def resume_mission(
    request: Request,
    mission_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        mission = svc.resume_mission(mission_id)
        return JSONResponse(_mission_to_response(mission))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def cancel_mission(
    request: Request,
    mission_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        mission = svc.cancel_mission(mission_id)
        return JSONResponse(_mission_to_response(mission))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ======================================================================
# RUNTIME HANDLERS
# ======================================================================


async def list_runtimes(request: Request) -> JSONResponse:
    svc = _get_service(request)
    runtimes = svc.list_runtimes()
    return JSONResponse({"runtimes": runtimes, "total": len(runtimes)})


async def runtime_health_summary(request: Request) -> JSONResponse:
    svc = _get_service(request)
    runtimes = svc.list_runtimes()
    health_summary: dict[str, int] = {"available": 0, "degraded": 0, "unavailable": 0, "unknown": 0}
    for r in runtimes:
        h = r.get("health", "unknown")
        health_summary[h] = health_summary.get(h, 0) + 1
    return JSONResponse(health_summary)


async def runtime_metrics(request: Request) -> JSONResponse:
    svc = _get_service(request)
    runtimes = svc.list_runtimes()
    result = {}
    for r in runtimes:
        result[r["name"]] = r.get("metrics", {})
    return JSONResponse(result)


async def get_runtime(request: Request, name: str) -> JSONResponse:
    svc = _get_service(request)
    runtimes = svc.list_runtimes()
    for r in runtimes:
        if r["name"] == name:
            return JSONResponse(r)
    raise HTTPException(status_code=404, detail=f"Runtime '{name}' not found.")


async def get_runtime_health(request: Request, name: str) -> JSONResponse:
    svc = _get_service(request)
    try:
        health = svc.runtime_health(name)
        return JSONResponse(health)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def get_runtime_metrics(request: Request, name: str) -> JSONResponse:
    svc = _get_service(request)
    try:
        metrics = svc.runtime_metrics(name)
        return JSONResponse({
            "runtime_name": metrics.runtime_name,
            "executions": metrics.executions,
            "successes": metrics.successes,
            "failures": metrics.failures,
            "avg_latency_ms": metrics.avg_latency_ms,
            "success_rate": metrics.success_rate,
            "reliability_score": metrics.reliability_score,
            "performance_score": metrics.performance_score,
        })
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ======================================================================
# EXECUTION HANDLERS
# ======================================================================


async def get_execution_status(request: Request) -> JSONResponse:
    svc = _get_service(request)
    status = svc.get_execution_status()
    # Serialize ExecutionStatistics if present
    if "statistics" in status and hasattr(status["statistics"], "executions_started"):
        stats = status["statistics"]
        status["statistics"] = {
            "executions_started": stats.executions_started,
            "executions_completed": stats.executions_completed,
            "executions_failed": stats.executions_failed,
            "tasks_executed": stats.tasks_executed,
            "tasks_parallel": stats.tasks_parallel,
            "avg_execution_time_ms": stats.avg_execution_time_ms,
            "success_rate": stats.success_rate,
            "avg_wait_time_ms": stats.avg_wait_time_ms,
            "recovery_count": stats.recovery_count,
        }
    return JSONResponse(status)


async def start_execution(
    request: Request,
    body: ExecutionStartRequest,
) -> JSONResponse:
    svc = _get_service(request)
    from backend.agent.supervisor import MissionContext
    from backend.agent.task_planner import PlannedTask

    tasks = []
    for t in body.tasks:
        tasks.append(PlannedTask(
            id=t.get("id", f"task_{time.time_ns()}"),
            title=t.get("title", "task"),
            runtime_capability=t.get("runtime_capability", "chat"),
            dependencies=frozenset(t.get("dependencies", [])),
        ))

    ctx = MissionContext(
        mission_id=body.mission_id,
        title=f"Execution {body.mission_id}",
        objective="Mission execution",
    )
    try:
        execution = svc.start_execution(ctx, tasks)
        return JSONResponse({
            "execution_id": execution.execution_id,
            "mission_id": execution.mission_id,
            "created_at": execution.created_at,
        }, status_code=201)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def pause_execution(request: Request) -> JSONResponse:
    svc = _get_service(request)
    try:
        svc.pause_execution()
        return JSONResponse({"status": "paused"})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def resume_execution(request: Request) -> JSONResponse:
    svc = _get_service(request)
    try:
        svc.resume_execution()
        return JSONResponse({"status": "resumed"})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def cancel_execution(request: Request) -> JSONResponse:
    svc = _get_service(request)
    try:
        svc.cancel_execution()
        return JSONResponse({"status": "cancelled"})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ======================================================================
# MEMORY HANDLERS
# ======================================================================


async def list_memory_entries(
    request: Request,
    scope: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> JSONResponse:
    svc = _get_service(request)
    from backend.memory.unified_memory import MemoryQuery
    result = svc.search_memory(MemoryQuery(
        scope=scope if scope else None,
        limit=limit,
    ))
    entries = [_memory_entry_to_response(e) for e in result.entries]
    return JSONResponse({"entries": entries, "total": result.total})


async def store_memory(
    request: Request,
    body: MemoryStoreRequest,
) -> JSONResponse:
    svc = _get_service(request)
    from backend.memory.unified_memory import MemoryScope
    try:
        scope = MemoryScope(body.scope)
    except ValueError:
        scope = body.scope
    entry = svc.store_memory(
        content=body.content,
        title=body.title,
        scope=scope,
        tags=frozenset(body.tags) if body.tags else None,
        importance=body.importance,
    )
    return JSONResponse(_memory_entry_to_response(entry), status_code=201)


async def get_memory_entry(
    request: Request,
    entry_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    entry = svc.get_memory(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Memory entry '{entry_id}' not found.")
    return JSONResponse(_memory_entry_to_response(entry))


async def update_memory_entry(
    request: Request,
    entry_id: str,
    body: MemoryStoreRequest,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        entry = svc.update_memory(
            entry_id,
            content=body.content,
            title=body.title,
            tags=frozenset(body.tags) if body.tags else None,
            importance=body.importance,
        )
        return JSONResponse(_memory_entry_to_response(entry))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def search_memory_entries(
    request: Request,
    q: str = Query("", description="Search text"),
    scope: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    svc = _get_service(request)
    from backend.memory.unified_memory import MemoryQuery, MemoryScope
    scope_val = None
    if scope:
        try:
            scope_val = MemoryScope(scope)
        except ValueError:
            scope_val = scope
    query = MemoryQuery(
        text=q if q else None,
        scope=scope_val,
        limit=limit,
        offset=offset,
    )
    result = svc.search_memory(query)
    entries = [_memory_entry_to_response(e) for e in result.entries]
    return JSONResponse({"entries": entries, "total": result.total, "execution_time_ms": result.execution_time_ms})


async def get_memory_statistics(request: Request) -> JSONResponse:
    svc = _get_service(request)
    stats = svc.get_memory_statistics()
    return JSONResponse({
        "total_entries": stats.total_entries,
        "per_scope": stats.per_scope,
        "total_searches": stats.total_searches,
        "avg_search_time_ms": stats.avg_search_time_ms,
    })


# ======================================================================
# SKILLS HANDLERS
# ======================================================================


async def list_registered_skills(request: Request) -> JSONResponse:
    svc = _get_service(request)
    skills = svc.list_skills()
    return JSONResponse({
        "skills": [_skill_to_response(s) for s in skills],
        "total": len(skills),
    })


async def select_skills(
    request: Request,
    body: SkillSelectRequest,
) -> JSONResponse:
    svc = _get_service(request)
    selection = svc.select_skills(
        required_capabilities=frozenset(body.required_capabilities) if body.required_capabilities else None,
        tags=frozenset(body.tags) if body.tags else None,
        preferred_ids=frozenset(body.preferred_ids) if body.preferred_ids else None,
    )
    return JSONResponse({
        "selected_skills": sorted(selection.selected_skills),
        "rejected_skills": sorted(selection.rejected_skills),
        "total_tokens": selection.total_tokens,
        "explanation": selection.explanation,
    })


async def recommend_skills(
    request: Request,
    body: dict[str, Any],
) -> JSONResponse:
    svc = _get_service(request)
    mission = body.get("mission_description", "")
    max_rec = body.get("max_recommendations", 5)
    skills = svc.recommend_skills(mission, max_recommendations=max_rec)
    return JSONResponse({
        "recommendations": [_skill_to_response(s) for s in skills],
    })


async def load_skill_bundle(
    request: Request,
    bundle_id: str,
) -> JSONResponse:
    svc = _get_service(request)
    try:
        count = svc.load_skill_bundle(bundle_id)
        return JSONResponse({"bundle_id": bundle_id, "skills_loaded": count})
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def get_skill_statistics(request: Request) -> JSONResponse:
    svc = _get_service(request)
    stats = svc.get_skill_statistics()
    return JSONResponse({
        "total_skills_registered": stats.total_skills_registered,
        "total_skills_loaded": stats.total_skills_loaded,
        "total_selections": stats.total_selections,
        "avg_selection_time_ms": stats.avg_selection_time_ms,
        "load_success_rate": stats.load_success_rate,
    })


# ======================================================================
# EVENTS HANDLERS
# ======================================================================


async def query_events(
    request: Request,
    types: Optional[str] = Query(None),
    sources: Optional[str] = Query(None),
    severities: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    svc = _get_service(request)
    from backend.events.system_event_bus import EventFilter

    filter_ = EventFilter(
        types=frozenset(t.strip() for t in types.split(",")) if types else None,
        sources=frozenset(s.strip() for s in sources.split(",")) if sources else None,
        severities=frozenset(s.strip() for s in severities.split(",")) if severities else None,
        limit=limit,
        offset=offset,
    )
    events = svc.query_events(filter_)
    return JSONResponse({
        "events": [
            {
                "id": e.id,
                "type": e.type.value if hasattr(e.type, "value") else str(e.type),
                "source": e.source,
                "timestamp": e.timestamp,
                "severity": e.severity.value if hasattr(e.severity, "value") else str(e.severity),
                "payload": e.payload,
                "correlation_id": e.correlation_id,
            }
            for e in events
        ],
        "total": len(events),
    })


async def get_event_statistics(request: Request) -> JSONResponse:
    svc = _get_service(request)
    stats = svc.get_bus_statistics()
    return JSONResponse({
        "total_published": stats.total_published,
        "total_consumed": stats.total_consumed,
        "subscriber_count": stats.subscriber_count,
        "avg_latency_ms": stats.avg_latency_ms,
        "events_by_type": stats.events_by_type,
        "history_size": stats.history_size,
    })


async def export_events(
    request: Request,
    types: Optional[str] = Query(None),
    sources: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
) -> JSONResponse:
    svc = _get_service(request)
    from backend.events.system_event_bus import EventFilter
    filter_ = EventFilter(
        types=frozenset(t.strip() for t in types.split(",")) if types else None,
        sources=frozenset(s.strip() for s in sources.split(",")) if sources else None,
        limit=limit,
    )
    exported = svc.export_events(filter_=filter_, indent=2)
    return JSONResponse({"export": exported})


async def publish_event(
    request: Request,
    body: dict[str, Any],
) -> JSONResponse:
    svc = _get_service(request)
    from backend.events.system_event_bus import SystemEventType, EventSeverity
    ev_type = body.get("type", "system")
    source = body.get("source", "api")
    try:
        ev_type = SystemEventType(ev_type)
    except ValueError:
        pass
    sev = body.get("severity", "info")
    try:
        sev = EventSeverity(sev)
    except ValueError:
        pass
    event = svc.publish_event(
        event_type=ev_type,
        source=source,
        payload=body.get("payload", {}),
        severity=sev,
    )
    return JSONResponse({
        "id": event.id,
        "type": event.type.value if hasattr(event.type, "value") else str(event.type),
        "source": event.source,
        "timestamp": event.timestamp,
        "severity": event.severity.value if hasattr(event.severity, "value") else str(event.severity),
    }, status_code=201)


async def clear_events(request: Request) -> JSONResponse:
    svc = _get_service(request)
    svc.clear_events()
    return JSONResponse({"status": "cleared"})


# ======================================================================
# HERMES AGENT HANDLERS
# ======================================================================


async def hermes_status(request: Request) -> JSONResponse:
    svc = _get_service(request)
    status = svc.hermes_health()
    return JSONResponse({"status": status})


async def hermes_connect(request: Request, body: HermesConnectRequest) -> JSONResponse:
    svc = _get_service(request)
    try:
        result = svc.connect_hermes_agent(base_url=body.base_url, timeout=body.timeout)
        return JSONResponse({"connected": result})
    except MissionControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def hermes_disconnect(request: Request) -> JSONResponse:
    svc = _get_service(request)
    result = svc.disconnect_hermes_agent()
    return JSONResponse({"disconnected": result})


async def hermes_execute_task(request: Request, body: HermesTaskRequest) -> JSONResponse:
    svc = _get_service(request)
    try:
        result = svc.execute_hermes_task(body.task_type, body.messages, session_id=body.session_id)
        return JSONResponse(result)
    except MissionControlError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def hermes_list_sessions(request: Request) -> JSONResponse:
    svc = _get_service(request)
    sessions = svc.list_hermes_sessions()
    return JSONResponse({"sessions": sessions})


# ======================================================================
# SYSTEM HANDLERS
# ======================================================================


async def health_check(request: Request) -> JSONResponse:
    """GET /api/v1/health — lightweight health check."""
    svc = _get_service(request)
    health = svc.health()
    return JSONResponse({
        "status": health.status.value if hasattr(health.status, "value") else str(health.status),
        "version": "0.1.0",
        "uptime_seconds": health.uptime,
        "kernel_status": health.kernel_status,
        "runtime_available": health.runtime_status.get("available", 0),
        "runtime_degraded": health.runtime_status.get("degraded", 0),
        "runtime_unavailable": health.runtime_status.get("unavailable", 0),
        "hermes_agent": health.integrations_status.get("hermes_agent", "unavailable"),
    })


async def system_status(request: Request) -> JSONResponse:
    """GET /api/v1/status — overall system status."""
    svc = _get_service(request)
    status = svc.status()
    health = svc.health()
    return JSONResponse({
        "status": status.value if hasattr(status, "value") else str(status),
        "uptime_seconds": health.uptime,
    })


async def system_diagnostics(request: Request) -> JSONResponse:
    """GET /api/v1/diagnostics — full system diagnostics."""
    svc = _get_service(request)
    diag = svc.diagnostics()
    return JSONResponse(diag)


async def system_statistics(request: Request) -> JSONResponse:
    """GET /api/v1/statistics — aggregated system statistics."""
    svc = _get_service(request)
    stats = svc.statistics()
    return JSONResponse({
        "missions": stats.missions,
        "agents": stats.agents,
        "runtimes": {k: {
            "executions": v.executions,
            "successes": v.successes,
            "failures": v.failures,
            "success_rate": v.success_rate,
        } for k, v in stats.runtimes.items()} if stats.runtimes else {},
        "events": stats.events,
        "uptime_seconds": stats.uptime_seconds,
    })


async def system_version(request: Request) -> JSONResponse:
    """GET /api/v1/version.

    HOS-234 : rendait `"0.1.0"` en dur, avec une liste de modules
    arrêtée à HOS-028 — donc une version qui ne désignait rien et une
    liste qui n'a plus été juste depuis deux cents jalons.

    La version produit existe depuis HOS-232, et la version **installée**
    depuis HOS-233. Les deux sont rendues, et elles peuvent différer :
    c'est précisément ce qu'on veut voir après une mise à jour dont le
    marquage n'a pas eu lieu.
    """
    from backend.maj.version import VERSION, lire_version_installee

    installee = lire_version_installee()
    return JSONResponse({
        "version": VERSION,
        # `None` et non la version du code : les confondre masquerait
        # exactement l'écart qu'on cherche.
        "version_installee": installee or None,
        "a_jour": bool(installee) and installee == VERSION,
    })


async def operations_apercu(request: Request) -> JSONResponse:
    """GET /api/v1/operations — ce que douze jalons ont produit.

    Registre des runs, fournisseurs et leurs écarts, approbations et
    leurs portées, points de reprise, version installée et santé. Rien
    n'était exposé avant HOS-234.
    """
    from backend.services import vue_operations

    return JSONResponse(vue_operations.vue_d_ensemble())


async def operations_runs(request: Request, mission: str) -> JSONResponse:
    """GET /api/v1/operations/missions/{mission}/runs."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.runs_de_la_mission(mission))


async def operations_lignee(request: Request, run: str) -> JSONResponse:
    """GET /api/v1/operations/runs/{run}/lignee.

    « Avec quel modèle, et pourquoi le premier essai a raté ? » — la
    question à laquelle la nuit du 29 au 30 août n'a pas su répondre.
    """
    from backend.services import vue_operations

    return JSONResponse(vue_operations.lignee(run))


async def operations_contrat(request: Request, run: str) -> JSONResponse:
    """GET /api/v1/operations/runs/{run}/contrat."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.contrat_du_run(run))


async def operations_checkpoints(request: Request,
                                 workspace: Optional[str] = Query(None)
                                 ) -> JSONResponse:
    """GET /api/v1/operations/checkpoints."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.points_de_reprise(workspace))


async def operations_fournisseurs(request: Request) -> JSONResponse:
    """GET /api/v1/operations/fournisseurs."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.fournisseurs())


async def operations_approbations(request: Request) -> JSONResponse:
    """GET /api/v1/operations/approbations."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.approbations())


async def operations_installation(request: Request) -> JSONResponse:
    """GET /api/v1/operations/installation."""
    from backend.services import vue_operations

    return JSONResponse(vue_operations.installation())


async def system_tick(request: Request) -> JSONResponse:
    """POST /api/v1/tick — advance all running missions."""
    svc = _get_service(request)
    changed = svc.tick_supervisor()
    return JSONResponse({"missions_changed": changed})
