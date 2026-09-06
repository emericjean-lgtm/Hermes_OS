"""Ce que le runtime agentique sait réellement faire, servi au cockpit (HOS-265).

Deux routes, et chacune a un appelant frontend réel — c'est la condition
posée par la règle anti-orphelin (`test_pas_de_backend_orphelin.py`), et
elle existe parce que HOS-235 a déjà livré huit routes correctes sur une
surface que personne ne montait : `GET /api/v1/operations` rendait `404`
alors que ses tests passaient, parce qu'ils montaient le routeur eux-mêmes.

Lecture et rafraîchissement, rien d'autre. Le pont ne décide rien : il
rapporte une **mesure** — quelles méthodes le gateway de Hermes Agent
répond réellement — et Hermes OS garde toutes ses autorités.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.bridge import HermesAgentBridge

router = APIRouter(tags=["bridge"])

#: Un pont par processus. Il ne porte aucun état de décision — seulement un
#: verrou et un cache de négociation — donc le partager est sans risque.
_pont = HermesAgentBridge()


@router.get("/bridge/capabilities",
            summary="Capacités réellement négociées avec Hermes Agent")
async def capacites() -> JSONResponse:
    """Ce que le runtime installé sert, mesuré et non supposé.

    Servi depuis le cache tant que l'empreinte du runtime n'a pas changé ;
    mettre l'agent à jour la change et force une nouvelle mesure.
    """
    return JSONResponse(_pont.negocier().as_dict())


@router.post("/bridge/capabilities/refresh",
             summary="Re-négocier maintenant")
async def rafraichir() -> JSONResponse:
    """Relance une vraie négociation contre le gateway (~4 s mesurées).

    Utile quand la configuration de l'agent a changé sans que sa version
    bouge — un serveur MCP ajouté, un toolset activé — car l'empreinte
    seule ne l'aurait pas vu.
    """
    return JSONResponse(_pont.negocier(forcer=True).as_dict())
