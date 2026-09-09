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
#: verrou, un cache de négociation et la connexion au gateway — donc le
#: partager est sans risque, et en ouvrir deux coûterait deux fois les
#: skills chargées et deux découvertes MCP pour un runtime qui n'a qu'un
#: seul état sur le disque.
_pont = HermesAgentBridge()


def pont() -> HermesAgentBridge:
    """Le pont partagé. Exposé pour que `vue_agent` parle au même.

    Une fonction plutôt que l'attribut : un second `HermesAgentBridge()`
    créé ailleurs ouvrirait un second gateway sans que rien ne le dise.
    """
    return _pont


@router.get("/bridge/capabilities",
            summary="Capacités réellement négociées avec Hermes Agent")
async def capacites() -> JSONResponse:
    """Ce que le runtime installé sert, mesuré et non supposé.

    Servi depuis le cache tant que l'empreinte du runtime n'a pas changé ;
    mettre l'agent à jour la change et force une nouvelle mesure.
    """
    return JSONResponse(_pont.negocier().as_dict())


@router.get("/bridge/agent", summary="Ce que le cerveau agentique porte")
async def vue_agent_complete() -> JSONResponse:
    """Sessions, outils, profils, délégation et routines en une lecture.

    Une seule route parce que le gateway coûte six secondes à froid : cinq
    appels frontend séparés rouvriraient la même connexion cinq fois.
    """
    from backend.services import vue_agent

    return JSONResponse(vue_agent.vue_d_ensemble())


@router.get("/bridge/agent/permissions",
            summary="Ce que Hermes OS a répondu quand l'agent a demandé à écrire")
async def permissions() -> JSONResponse:
    """Observation seule : la décision reste dans l'adaptateur ACP.

    Le contrôle agit vraiment — mesuré, deux refus sur un seul tour — et
    n'avait aucun témoin. Un refus visible ici ne prouve pas qu'une
    écriture a été empêchée : le terminal de l'agent ne demande aucune
    permission, et il peut réessayer par là.
    """
    from backend.security import journal_permissions

    return JSONResponse(journal_permissions.decisions())


@router.get("/bridge/agent/sessions/{cle}/historique",
            summary="Les messages d'une session stockée")
async def historique(cle: str) -> JSONResponse:
    """Lecture. L'activation prealable n'ecrit rien (mesure G-18)."""
    from backend.services import vue_agent

    return JSONResponse(vue_agent.historique(cle))


@router.post("/bridge/agent/sessions/{cle}/titre",
             summary="Demander à l'agent de renommer une session")
async def renommer(cle: str, corps: dict | None = None) -> JSONResponse:
    from backend.services import mutations_agent

    return JSONResponse(
        mutations_agent.renommer_session(cle, str((corps or {}).get("titre") or "")))


@router.post("/bridge/agent/toolsets/{nom}",
             summary="Activer ou désactiver un toolset du cerveau")
async def basculer_toolset(nom: str, corps: dict | None = None) -> JSONResponse:
    """Écrit `config.yaml` côté agent — donc porte sur les missions.

    Le premier appel fige les défauts du jour dans le fichier : le
    round-trip YAML matérialise les toolsets implicites. Rien n'est perdu.
    """
    from backend.services import mutations_agent

    actif = bool((corps or {}).get("actif"))
    return JSONResponse(mutations_agent.basculer_toolset(nom, actif))


@router.post("/bridge/agent/sessions/{cle}/brancher",
             summary="Demander à l'agent de brancher une session")
async def brancher(cle: str, corps: dict | None = None) -> JSONResponse:
    """La seule mutation intégrée, et elle appartient à l'agent (G-18).

    Hermes OS n'ouvre pas `state.db` : il demande. Un refus du runtime
    revient en `200` avec `applique: false` et sa raison — c'est un
    résultat, pas une panne, et l'interface doit pouvoir le distinguer
    d'une erreur de transport.
    """
    from backend.services import mutations_agent

    titre = str((corps or {}).get("titre") or "")
    return JSONResponse(mutations_agent.brancher_session(cle, titre))


@router.post("/bridge/capabilities/refresh",
             summary="Re-négocier maintenant")
async def rafraichir() -> JSONResponse:
    """Relance une vraie négociation contre le gateway (~4 s mesurées).

    Utile quand la configuration de l'agent a changé sans que sa version
    bouge — un serveur MCP ajouté, un toolset activé — car l'empreinte
    seule ne l'aurait pas vu.
    """
    return JSONResponse(_pont.negocier(forcer=True).as_dict())


@router.get("/bridge/agent/skills/catalogue",
            summary="Une page du hub de Skills")
async def skills_catalogue(page: int = 1) -> JSONResponse:
    """Le hub distant — 5493 entrées mesurées — et non l'installation.

    Population distincte de `/skills` : les deux ne se recouvrent qu'à la
    marge, et les afficher ensemble laisserait croire qu'une entrée du
    catalogue est installée.
    """
    from backend.services import vue_skills

    return JSONResponse(vue_skills.catalogue(page))


@router.get("/bridge/agent/skills/recherche",
            summary="Chercher une Skill dans le hub")
async def skills_recherche(q: str = "") -> JSONResponse:
    from backend.services import vue_skills

    return JSONResponse(vue_skills.rechercher(q))


@router.get("/bridge/agent/skills/detail",
            summary="Le détail d'une entrée du catalogue")
async def skills_detail(nom: str = "") -> JSONResponse:
    """`connu: false` n'est pas une panne : le hub ignore ce nom.

    Une Skill installée hors hub tombe là, et l'interface doit le dire
    plutôt que d'ouvrir un panneau vide.
    """
    from backend.services import vue_skills

    return JSONResponse(vue_skills.detail(nom))
