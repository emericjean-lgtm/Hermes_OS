"""Alexandrie integration REST API — HOS-053B production."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.integrations.alexandrie.alexandrie_models import AlexandrieNode, AlexandrieNodeType, ConflictResolution
from backend.integrations.alexandrie.hermes_alexandrie_adapter import get_alexandrie_adapter

router = APIRouter(prefix="/alexandrie", tags=["alexandrie"])


@router.get("/health")
def health():
    return get_alexandrie_adapter().health_check()


@router.get("/status")
def status():
    return get_alexandrie_adapter().get_status()


# ── Documents ──────────────────────────────────────────────────────

@router.get("/documents")
def list_documents(user_id: str = Query(default="")):
    adapter = get_alexandrie_adapter()
    nodes = adapter.client.list_nodes(user_id) if user_id else []
    return {"total": len(nodes), "documents": [_node_to_dict(n) for n in nodes]}


@router.get("/documents/{node_id}")
def get_document(node_id: str):
    node = get_alexandrie_adapter().get_document(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _node_to_dict(node)


@router.post("/documents")
def create_document(body: dict):
    adapter = get_alexandrie_adapter()
    node = adapter.create_document(
        title=body.get("title", ""),
        content=body.get("content", ""),
        user_id=body.get("user_id", ""),
        is_public=body.get("is_public", False),
    )
    if node is None:
        raise HTTPException(status_code=500, detail="Failed to create document")
    return _node_to_dict(node)


@router.put("/documents/{node_id}")
def update_document(node_id: str, body: dict):
    node = get_alexandrie_adapter().update_document(node_id=node_id, title=body.get("title", ""), content=body.get("content", ""))
    if node is None:
        raise HTTPException(status_code=404, detail="Document not found or update failed")
    return _node_to_dict(node)


@router.delete("/documents/{node_id}")
def delete_document(node_id: str):
    if not get_alexandrie_adapter().delete_document(node_id):
        raise HTTPException(status_code=404, detail="Document not found or delete failed")
    return {"status": "deleted", "id": node_id}


# ── Search ─────────────────────────────────────────────────────────

@router.get("/search")
def search(q: str = Query(default="", min_length=2), limit: int = Query(default=20, ge=1, le=100), mode: str = Query(default="hybrid")):
    adapter = get_alexandrie_adapter()
    if mode == "fulltext":
        r = adapter.full_text_search(q, limit)
        return {"query": q, "mode": "fulltext", "total": r.total, "took_ms": r.took_ms, "results": [_node_to_dict(n) for n in r.nodes]}
    if mode == "semantic":
        entries = adapter.semantic_search(q, limit)
        return {"query": q, "mode": "semantic", "total": len(entries), "results": [{"id": e.external_id, "title": e.title, "content": e.content[:500], "source": "hermes"} for e in entries]}
    r = adapter.hybrid_search(q, limit)
    return {"query": q, "mode": "hybrid", "total": r.total, "results": r.merged_results}


# ── Sync ───────────────────────────────────────────────────────────

@router.post("/sync")
def sync_documents(body: dict):
    adapter = get_alexandrie_adapter()
    result = adapter.sync_all_documents(user_id=body.get("user_id", ""), incremental=body.get("incremental", True))
    return result


@router.get("/sync/status")
def sync_status():
    adapter = get_alexandrie_adapter()
    return {"last_sync_at": adapter._last_sync_at.isoformat() if adapter._last_sync_at else None, "documents_synced": len(adapter._external_index)}


@router.get("/sync/history")
def sync_history(limit: int = Query(default=50)):
    return {"events": get_alexandrie_adapter().get_sync_history(limit)}


@router.post("/sync/mark-outdated")
def mark_outdated(body: dict):
    ok = get_alexandrie_adapter().mark_outdated(body.get("document_id", ""))
    return {"marked": ok}


# ── Missions ───────────────────────────────────────────────────────

@router.post("/missions/link")
def link_to_mission(body: dict):
    ok = get_alexandrie_adapter().link_document_to_mission(body["document_id"], body["mission_id"])
    return {"linked": ok}


@router.get("/missions/{mission_id}/documents")
def mission_documents(mission_id: str):
    return {"mission_id": mission_id, "documents": get_alexandrie_adapter().get_mission_documents(mission_id)}


@router.post("/missions/relevant")
def relevant_documents(body: dict):
    docs = get_alexandrie_adapter().find_relevant_documents(body.get("tags", []), body.get("limit", 10))
    return {"documents": docs}


# ── Graph ──────────────────────────────────────────────────────────

@router.get("/graph")
def get_graph(node_id: Optional[str] = Query(default=None)):
    adapter = get_alexandrie_adapter()
    edges = adapter.get_graph_for_node(node_id) if node_id else adapter.get_graph_edges()
    return {"total": len(edges), "edges": edges}


# ── Cache ──────────────────────────────────────────────────────────

@router.get("/cache/stats")
def cache_stats():
    return get_alexandrie_adapter().cache_stats()


@router.post("/cache/prune")
def prune_cache():
    removed = get_alexandrie_adapter().prune_cache()
    return {"removed": removed}


# ── Events ─────────────────────────────────────────────────────────

@router.get("/events")
def get_events(limit: int = Query(default=50, ge=1, le=500)):
    adapter = get_alexandrie_adapter()
    return {"total": len(adapter.get_events(limit)), "events": adapter.get_events(limit)}


# ── Helper ─────────────────────────────────────────────────────────

def _node_to_dict(node: AlexandrieNode) -> dict:
    return {
        "id": node.id, "title": node.title, "content": node.content[:1000] if node.content else "",
        "node_type": node.node_type.value, "parent_id": node.parent_id,
        "owner_id": node.owner_id, "is_public": node.is_public,
        "version": node.version, "tags": node.tags,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }
