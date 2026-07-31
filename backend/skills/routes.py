"""REST API routes for skill distribution (HOS-048)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from .skill_cache import SkillCache
from .skill_distributor import SkillDistributor
from .skill_loader import SkillLoader
from .skill_models import (
    SkillDefinition,
    SkillDistribution,
    SkillProfile,
    SkillSelection,
)
from .skill_profiler import SkillProfiler
from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector

# ── Global instances ─────────────────────────────────────────

_registry = SkillRegistry()
_profiler = SkillProfiler()
_cache = SkillCache(max_size=50)
_loader = SkillLoader(_registry)
_selector = SkillSelector(_registry)
from .dependency_resolver import SkillDependencyResolver
_resolver = SkillDependencyResolver(_registry)
_distributor = SkillDistributor(_registry, _selector, _resolver, _loader, _cache, _profiler)


# ── Helper to simulate HTTP routing (pure function interface) ─

def handle_get_skills(category: Optional[str] = None, domain: Optional[str] = None,
                      status: Optional[str] = None, tag: Optional[str] = None) -> dict:
    """GET /skills"""
    skills: list[dict] = []
    for skill in _registry.list_all():
        if category and skill.category.value != category:
            continue
        if domain and skill.domain.value != domain:
            continue
        if status and skill.status.value != status:
            continue
        if tag and tag not in skill.tags:
            continue
        skills.append(_skill_to_dict(skill))
    return {"skills": skills, "count": len(skills), "stats": _registry.stats()}


def handle_get_skill(skill_id: str) -> Optional[dict]:
    """GET /skills/{id}"""
    skill = _registry.get(skill_id)
    if skill is None:
        return None
    instances = _loader.get_loaded(skill_id)
    profile = _profiler.get(skill_id)
    return {
        "skill": _skill_to_dict(skill),
        "instances": len(instances),
        "profile": _profile_to_dict(profile) if profile else None,
    }


def handle_post_select(task_description: str = "", categories: Optional[list[str]] = None,
                       technologies: Optional[list[str]] = None,
                       agent_capabilities: Optional[list[str]] = None,
                       max_skills: int = 10) -> dict:
    """POST /skills/select"""
    selections = _selector.select(
        task_description=task_description,
        categories=categories,
        technologies=technologies,
        agent_capabilities=agent_capabilities,
        max_skills=max_skills,
    )
    return {
        "selections": [_selection_to_dict(s) for s in selections],
        "count": len(selections),
    }


def handle_post_load(skill_id: str, agent_id: str = "", mission_id: str = "") -> dict:
    """POST /skills/load"""
    instance = _loader.load(skill_id, agent_id=agent_id, mission_id=mission_id)
    if instance is None:
        return {"error": f"Skill {skill_id} not found", "loaded": False}
    _cache.put(skill_id)
    return {"instance_id": instance.id, "skill_id": skill_id, "state": instance.load_state.value, "loaded": True}


def handle_post_unload(skill_id: str) -> dict:
    """POST /skills/unload"""
    count = 0
    for inst in _loader.get_loaded(skill_id):
        if _loader.unload(inst.id):
            _cache.evict(skill_id)
            count += 1
    return {"skill_id": skill_id, "unloaded": count}


def handle_get_cache() -> dict:
    """GET /skills/cache"""
    return _cache.stats()


def handle_get_statistics() -> dict:
    """GET /skills/statistics"""
    return {
        "registry": _registry.stats(),
        "cache": _cache.stats(),
        "loader": _loader.stats(),
        "profiler": _profiler.stats(),
        "distributor": _distributor.stats(),
    }


def handle_post_distribute(mission_id: str, agent_tasks: dict) -> dict:
    """POST /skills/distribute"""
    distribution = _distributor.distribute(mission_id, agent_tasks)
    return _distribution_to_dict(distribution)


# ── Serialization helpers ────────────────────────────────────

def _skill_to_dict(s: SkillDefinition) -> dict:
    return {
        "id": s.id, "name": s.name, "version": s.version,
        "category": s.category.value, "domain": s.domain.value,
        "tags": s.tags, "technologies": s.technologies,
        "dependencies": s.dependencies, "status": s.status.value,
        "memory_cost_mb": s.memory_cost_mb, "token_cost_estimate": s.token_cost_estimate,
        "quality_score": s.quality_score, "success_rate": s.success_rate,
        "usage_count": s.usage_count,
    }


def _selection_to_dict(s: SkillSelection) -> dict:
    return {
        "skill_id": s.skill_id, "skill_name": s.skill_name,
        "relevance_score": s.relevance_score, "justification": s.justification,
        "priority": s.priority, "estimated_cost_mb": s.estimated_cost_mb,
        "estimated_tokens": s.estimated_tokens,
    }


def _profile_to_dict(p: SkillProfile) -> dict:
    return {
        "skill_id": p.skill_id, "avg_load_time_ms": p.avg_load_time_ms,
        "avg_memory_mb": p.avg_memory_mb, "avg_tokens": p.avg_tokens,
        "failure_rate": p.failure_rate, "sample_count": p.sample_count,
    }


def _distribution_to_dict(d: SkillDistribution) -> dict:
    return {
        "id": d.id, "mission_id": d.mission_id,
        "agents": len(d.assignments),
        "total_memory_mb": d.total_memory_mb,
        "total_tokens": d.total_tokens,
        "assignments": {
            agent_id: [_selection_to_dict(s) for s in skills]
            for agent_id, skills in d.assignments.items()
        },
    }


# ── HTTP surface ─────────────────────────────────────────────
# Thin delegation to the handlers above (HOS-066B). The distributor and its
# registry/selector/loader/cache/profiler are the module-level instances built
# at the top of this file; create_skill_routes() takes the same object from the
# container so both access paths share one graph.

router = APIRouter(prefix="/skills", tags=["skills"])


def create_skill_routes(distributor: SkillDistributor) -> APIRouter:
    """Bind the container-owned distributor to these routes."""
    global _distributor
    _distributor = distributor
    return router


@router.get("")
async def get_skills(
    category: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
) -> dict:
    return handle_get_skills(category, domain, status, tag)


@router.get("/cache")
async def get_cache() -> dict:
    return handle_get_cache()


@router.get("/statistics")
async def get_statistics() -> dict:
    return handle_get_statistics()


@router.post("/select")
async def select_skills(payload: dict = Body(default_factory=dict)) -> dict:
    return handle_post_select(
        task_description=payload.get("task_description", ""),
        categories=payload.get("categories"),
        technologies=payload.get("technologies"),
        agent_capabilities=payload.get("agent_capabilities"),
        max_skills=int(payload.get("max_skills", 10)),
    )


@router.post("/load")
async def load_skill(payload: dict = Body(...)) -> dict:
    return handle_post_load(
        skill_id=payload.get("skill_id", ""),
        agent_id=payload.get("agent_id", ""),
        mission_id=payload.get("mission_id", ""),
    )


@router.post("/unload")
async def unload_skill(payload: dict = Body(...)) -> dict:
    return handle_post_unload(payload.get("skill_id", ""))


@router.post("/distribute")
async def distribute(payload: dict = Body(...)) -> dict:
    return handle_post_distribute(
        mission_id=payload.get("mission_id", ""),
        agent_tasks=payload.get("agent_tasks", {}),
    )


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict:
    result = handle_get_skill(skill_id)
    if result is None:
        raise HTTPException(404, f"skill {skill_id!r} not found")
    return result
