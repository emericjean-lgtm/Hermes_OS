"""Document ingestion endpoints — cahier des charges §13, §9.

REST counterpart of the documents_index MCP tool. Mirrors /memory/index's
shape, with one deliberate difference: this takes a *path* and does the
extraction itself, where /memory/index takes text the caller already
extracted.

The Aegis gate is the same `file_read` check every other file operation
goes through (backend/tools/file_tools.read_bytes) — a path outside
ALLOWED_PATHS is refused here exactly as it would be from MCP, so this
route adds an entry point, not a bypass.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.core.agent_registry import get_agent_registry
from backend.documents.extractor import (
    MissingExtractorDependencyError,
    UnsupportedDocumentError,
    extract_text,
    supported_suffixes,
)
from backend.tools import file_tools

router = APIRouter()


def _aegis() -> AegisAgent:
    return get_agent_registry().get("aegis")


def _echo():
    return get_agent_registry().get("echo")


class IndexFileRequest(BaseModel):
    path: str
    doc_id: str | None = None
    metadata: dict = {}
    project_id: str | None = None


class IndexFileResponse(BaseModel):
    indexed: bool
    chunks: int
    format: str
    units: int
    warnings: list[str] = []
    characters: int = 0
    reason: str | None = None


@router.get("/documents/formats")
async def list_formats() -> dict:
    """What /documents/index will accept. Images are excluded on purpose:
    use the vision agent (analyze_image) for those."""
    return {"supported": sorted(supported_suffixes())}


@router.post("/documents/index")
async def index_file(request: IndexFileRequest) -> IndexFileResponse:
    from pathlib import Path

    try:
        data = file_tools.read_bytes(_aegis(), request.path, project_id=request.project_id)
    except PermissionError as exc:
        # Aegis refused — 403, not 500: the request was understood and
        # deliberately denied.
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        extracted = extract_text(request.path, data=data)
    except UnsupportedDocumentError as exc:
        # 415: the format will never work here, retrying won't help.
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except MissingExtractorDependencyError as exc:
        # 501: the format is supported, this install just lacks the
        # library — a different problem, needing a different reaction.
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if not extracted.text.strip():
        return IndexFileResponse(
            indexed=False,
            chunks=0,
            format=extracted.format,
            units=extracted.units,
            warnings=list(extracted.warnings),
            reason="no extractable text",
        )

    chunks = _echo().index_document(
        request.doc_id or Path(request.path).name,
        extracted.text,
        {**request.metadata, "source_path": request.path, "format": extracted.format},
        project_id=request.project_id,
    )
    return IndexFileResponse(
        indexed=True,
        chunks=chunks,
        format=extracted.format,
        units=extracted.units,
        warnings=list(extracted.warnings),
        characters=len(extracted.text),
    )
