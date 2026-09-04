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
from backend.memory.confiance import provenance_de
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
    #: Metadonnee libre, ecrite par l'appelant. **N'autorise rien** :
    #: le filtre de quarantaine ne la lit pas (HOS-249).
    confidence: float
    created_at: str
    # ── Provenance (HOS-250) ─────────────────────────────────────────
    #: Ce qu'il faut pour qu'un operateur sache quoi promouvoir : d'ou
    #: vient la memoire, si elle est en quarantaine, et qui l'a validee.
    #: Sans ces trois champs, la route de promotion existe et personne ne
    #: peut savoir sur quoi l'appeler.
    origine: str | None = None
    en_quarantaine: bool = False
    promu_par: str | None = None
    verifie_le: str | None = None


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
        origine=entry.origine,
        # Derivee de la provenance, jamais d'une colonne propre : une
        # colonne d'etat serait modifiable sans changer l'origine,
        # c'est-a-dire promouvable sans acteur.
        en_quarantaine=provenance_de(entry).en_quarantaine,
        promu_par=entry.promu_par,
        verifie_le=entry.verifie_le.isoformat() if entry.verifie_le else None,
    )


@router.post("/memory")
async def create_memory(request: MemoryCreateRequest) -> MemoryResponse:
    # HOS-249 : cette route est celle d'un **humain** — le Cockpit, un
    # appel direct de l'operateur. `HUMAIN` est dans
    # `ORIGINES_DE_CONFIANCE`, donc ce qui est ecrit ici est utilisable
    # par l'agent sans promotion. C'est la difference avec le chemin MCP,
    # ou c'est le modele qui ecrit depuis ce qu'il a lu.
    from backend.memory.confiance import Origine

    entry = _echo().remember(
        type_=request.type,
        content=request.content,
        tags=request.tags,
        confidence=request.confidence,
        project_id=request.project_id,
        origine=Origine.HUMAIN,
    )
    return _to_response(entry)


class MemoryPromoteRequest(BaseModel):
    """Qui sort cette memoire de quarantaine.

    `promu_par` est **obligatoire et non vide** : la regle de
    `Provenance.promouvoir` est qu'une promotion sans acteur nomme n'est
    pas une promotion.

    ## Ce que ce nom prouve, et ce qu'il ne prouve pas

    Il ne prouve **rien** cryptographiquement : Hermes OS n'a pas de
    mecanisme d'identite humaine, et son conventionnel d'accord humain
    existant — `POST /security/approvals/{id}` — n'en porte pas non plus.
    Ce qui fait foi ici est le **canal** : cette route est servie par
    l'API locale et n'existe pas comme outil MCP, donc l'agent ne peut
    pas l'appeler.

    Le nom est une trace d'audit, pas une preuve. C'est exactement le
    modele de confiance deja retenu pour les approbations Aegis, et
    l'ecrire ici evite qu'on croie a une garantie plus forte.
    """

    promu_par: str


@router.post("/memory/{memory_id}/promote")
async def promote_memory(memory_id: str, request: MemoryPromoteRequest) -> MemoryResponse:
    """Sortir une memoire de quarantaine, en nommant qui l'a decide.

    Une memoire d'origine `AGENT`, `WEB` ou `INCONNUE` n'est jamais
    rendue au chemin agent. Cette route est la seule sortie, et elle est
    humaine par construction : **aucun outil MCP ne l'expose**.

    L'origine initiale n'est pas modifiee — une memoire ecrite par
    l'agent reste `agent` pour toujours. Ce qui change est la confiance,
    et `promu_par` porte la trace de qui en a decide.
    """
    from backend.memory.confiance import PromotionRefusee
    from backend.memory.episodic import DejaPromue

    try:
        entry = _echo().promouvoir(memory_id, par=request.promu_par)
    except PromotionRefusee as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"No memory entry {memory_id!r}") from exc
    except DejaPromue as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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


@router.get("/memory/permanent")
async def permanent_memory() -> list[dict]:
    """The permanent level only (§12) — entries belonging to no project.
    Distinct from GET /memory, which filters nothing and therefore mixes
    every project's entries in."""
    return _echo().permanent_memory()


@router.get("/memory/types")
async def memory_types() -> dict:
    """The §12 vocabulary. Guidance, not a whitelist: memory_remember
    still accepts any type string."""
    return project_memory.known_types()
