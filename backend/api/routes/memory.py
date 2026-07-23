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
from backend.memory.episodic import MemoryEntry

router = APIRouter()


class MemoryCreateRequest(BaseModel):
    type: str
    content: str
    tags: list[str] = []
    confidence: float = 1.0


class MemoryResponse(BaseModel):
    id: str
    type: str
    content: str
    tags: list[str]
    confidence: float
    created_at: str


class IndexDocumentRequest(BaseModel):
    doc_id: str
    text: str
    metadata: dict = {}


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
    )
    return _to_response(entry)


@router.get("/memory")
async def list_memory(type: str | None = None) -> list[MemoryResponse]:
    entries = _echo().list_memories(type_=type)
    return [_to_response(e) for e in entries]


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str) -> dict:
    deleted = _echo().forget(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No memory entry {memory_id!r}")
    return {"deleted": True, "id": memory_id}


@router.post("/memory/index")
async def index_document(request: IndexDocumentRequest) -> IndexDocumentResponse:
    chunks = _echo().index_document(request.doc_id, request.text, request.metadata)
    return IndexDocumentResponse(doc_id=request.doc_id, chunks_indexed=chunks)


@router.get("/memory/search")
async def search_memory(query: str, n_results: int = 5) -> list[SearchResult]:
    results = _echo().recall(query, n_results=n_results)
    return [SearchResult(**r) for r in results]
