"""Memory endpoints — cahier des charges §24.1 (subset: POST /memory,
DELETE /memory/{id}, GET /memory/search), plus GET /memory to list
entries and POST /memory/index to feed the documentary store — both
needed to exercise the full remember -> index -> recall loop, not just
listed verbatim in the §24.1 sketch. Every operation goes through
EchoAgent, never episodic.py/semantic.py directly.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.echo import EchoAgent
from backend.core.agent_registry import get_agent_registry
from backend.memory import project_memory
from backend.memory.episodic import MemoryEntry

router = APIRouter()


class MemoryCreateRequest(BaseModel):
    type: str
    content: str
    tags: list[str] = []
    confidence: float = 1.0
    project_id: str | None = None


class MemoryResponse(BaseModel):
    id: str
    project_id: str | None
    type: str
    content: str
    tags: list[str]
    confidence: float
    created_at: str


class IndexDocumentRequest(BaseModel):
    doc_id: str
    text: str
    metadata: dict = {}
    project_id: str | None = None


class IndexDocumentResponse(BaseModel):
    doc_id: str
    chunks_indexed: int


class SearchResult(BaseModel):
    id: str
    content: str
    metadata: dict
    distance: float | None = None


def _echo() -> EchoAgent:
    return get_agent_registry().get("echo")


def _to_response(entry: MemoryEntry) -> MemoryResponse:
    return MemoryResponse(
        id=entry.id,
        project_id=entry.project_id,
        type=entry.type,
        content=entry.content,
        tags=[t for t in entry.tags.split(",") if t],
        confidence=entry.confidence,
        created_at=entry.created_at.isoformat(),
    )


@router.post("/memory")
async def create_memory(request: MemoryCreateRequest) -> MemoryResponse:
    entry = _echo().remember(
        type_=request.type,
        content=request.content,
        tags=request.tags,
        confidence=request.confidence,
        project_id=request.project_id,
    )
    return _to_response(entry)


@router.get("/memory")
async def list_memory(type: str | None = None, project_id: str | None = None) -> list[MemoryResponse]:
    entries = _echo().list_memories(type_=type, project_id=project_id)
    return [_to_response(e) for e in entries]


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> dict:
    deleted = _echo().forget(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No memory entry {memory_id!r}")
    return {"deleted": True, "id": memory_id}


@router.post("/memory/index")
async def index_document(request: IndexDocumentRequest) -> IndexDocumentResponse:
    chunks = _echo().index_document(
        request.doc_id, request.text, request.metadata, project_id=request.project_id
    )
    return IndexDocumentResponse(doc_id=request.doc_id, chunks_indexed=chunks)


@router.get("/memory/search")
async def search_memory(
    query: str, n_results: int = 5, project_id: str | None = None
) -> list[SearchResult]:
    results = _echo().recall(query, n_results=n_results, project_id=project_id)
    return [SearchResult(**r) for r in results]

@router.get("/memory/project/{project_id}")
async def project_brief(project_id: str) -> dict:
    """A project's memory grouped by the §12 kinds (architecture,
    roadmap, decision, documentation), rather than one flat list — the
    shape an agent needs before starting work on a project."""
    brief = _echo().project_brief(project_id)
    return {
        "project_id": brief.project_id,
        "by_type": brief.by_type,
        "other": brief.other,
        "total": brief.total,
    }


@router.get("/memory/types")
async def memory_types() -> dict:
    """The §12 vocabulary. Guidance, not a whitelist: memory_remember
    still accepts any type string."""
    return project_memory.known_types()
