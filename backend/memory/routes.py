"""FastAPI routes for the Unified Memory (HOS-047)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body

from backend.memory.memory_manager import MemoryManager

router = APIRouter(prefix="/memory", tags=["memory"])

_manager: Optional[MemoryManager] = None


def create_memory_routes(manager: MemoryManager) -> APIRouter:
    global _manager
    _manager = manager
    return router


def _ensure():
    if _manager is None:
        from fastapi import HTTPException
        raise HTTPException(503, "Memory manager not initialized")


@router.post("/search")
async def search(payload: dict = Body(...)):
    _ensure()
    results = _manager.search(
        query=payload["query"],
        limit=payload.get("limit", 20),
        memory_types=payload.get("memory_types"),
    )
    return {
        "results": [
            {"type": r.source_type, "title": r.title, "snippet": r.snippet,
             "score": r.score, "justification": r.justification}
            for r in results
        ],
        "total": len(results),
    }


@router.get("/search")
async def search_get(q: str = "", limit: int = 20):
    _ensure()
    if not q:
        return {"results": [], "total": 0}
    results = _manager.search(query=q, limit=limit)
    return {
        "results": [
            {"type": r.source_type, "title": r.title, "snippet": r.snippet,
             "score": r.score}
            for r in results
        ],
        "total": len(results),
    }


@router.get("/graph")
async def get_graph(node_id: str = "", max_depth: int = 3):
    _ensure()
    if node_id:
        return _manager.traverse_graph(node_id, max_depth)
    return {"nodes": [], "edges": []}


@router.get("/experiences")
async def get_experiences(mission_type: str = "", tags: str = "", limit: int = 10):
    _ensure()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    recommendations = _manager.recommend_for_mission(mission_type, tag_list)
    return {"recommendations": recommendations}


@router.post("/index")
async def index_text(payload: dict = Body(...)):
    _ensure()
    vec = _manager.index_text(
        payload.get("entity_id", ""),
        payload.get("text", ""),
    )
    return {"entity_id": payload.get("entity_id"), "dimensions": len(vec)}


@router.get("/statistics")
async def get_statistics():
    _ensure()
    return _manager.stats()
