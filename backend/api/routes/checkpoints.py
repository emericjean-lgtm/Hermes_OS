"""Revenir en arrière : le chemin opérateur des points de reprise (HOS-291).

## Le défaut que ce module ferme

A-3, ouvert depuis HOS-223 et mesuré à chaque audit depuis : `prendre`
avait **un** appelant — `GraphExecutor._prendre_le_filet`, qui pose un
filet avant que toute mission touche au disque — et `restaurer` en avait
**zéro**. Aucune route, aucun outil MCP, aucun script. Le dépôt prenait
donc un point de reprise par mission, les listait dans le Center
« Supervision », et ne savait y revenir par aucun chemin.

C'est la forme la plus coûteuse de capacité fantôme : elle n'est pas
absente, elle est *visible*. Un opérateur qui voit « 14 points de
reprise » en conclut qu'il peut annuler, et ne découvre le contraire
qu'au moment où il en a besoin.

## Pourquoi un module, et pas une route de plus sur `/operations`

`backend/api/routes/operations.py` est en lecture seule **par contrat**,
et deux gardes le tiennent : toutes ses routes sont en `GET`, et un test
sur l'arbre syntaxique interdit à `vue_operations` d'appeler quoi que ce
soit qui commence par `prendre`, `restaurer` ou `appliquer`. La raison
est écrite dans son en-tête : une vue qui écrit devient un second chemin
vers l'état, et deux chemins vers l'état, c'est la question « lequel fait
foi ? » à chaque incident.

La lecture reste donc là où elle est — `GET /operations/checkpoints`
alimente déjà le panneau — et la mutation vit ici, comme
`routes/snapshots.py` le fait pour la moitié « état » de la même
capacité. Deux modules symétriques pour deux moitiés d'un même geste.

## Aegis décide, ce module ne décide pas

`data_migration` est `mandatory_validation` dans `config/security.yaml` :
le moteur rend donc **toujours** `require_human_validation` au premier
passage, et `AegisAgent` dépose une demande d'accord dans la file que le
Security Center sert déjà. Un second appel, après qu'un humain a décidé,
consomme l'accord et restaure.

Ce n'est pas un contournement à documenter : c'est le contrat. La
restauration est en deux temps *par construction*, et un refus au premier
appel est l'issue attendue, pas une panne. D'où un `200` portant
`restaure: false` et le verdict, sur le modèle de `routes/snapshots.py`
et de `file_tools.propose_write` — réserver un `4xx` à ce cas ferait lire
une gouvernance qui fonctionne comme une erreur.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.aegis import AegisAgent
from backend.checkpoints import checkpoint as _checkpoint
from backend.core.agent_registry import AgentNotFoundError, get_agent_registry

router = APIRouter(tags=["checkpoints"])


def _aegis() -> AegisAgent:
    try:
        return get_agent_registry().get("aegis")
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class RestaurerRequest(BaseModel):
    project_id: str | None = None


def _introuvable(identifiant: str) -> HTTPException:
    return HTTPException(status_code=404,
                         detail=f"Aucun point de reprise {identifiant!r}")


@router.get("/checkpoints/{identifiant}/apercu",
            summary="Ce que la restauration ferait, sans rien faire")
async def apercu(identifiant: str) -> dict:
    """Le contrat §14.1 appliqué au workspace : montrer la différence
    avant de l'appliquer.

    Les trois listes restent **séparées**. Fondre « à supprimer » dans un
    compteur de fichiers touchés ferait disparaître la seule des trois qui
    détruise du travail.
    """
    try:
        vue = _checkpoint.apercu(identifiant)
    except _checkpoint.CheckpointIntrouvable as exc:
        raise _introuvable(identifiant) from exc
    except _checkpoint.CheckpointImpossible as exc:
        # Le point de reprise existe mais n'est plus utilisable — une
        # référence git supprimée, par exemple. C'est un conflit d'état,
        # pas une absence : le dire autrement enverrait chercher un
        # identifiant correct.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "checkpoint": vue.checkpoint,
        "workspace": vue.workspace,
        "a_restaurer": list(vue.a_restaurer),
        "a_recreer": list(vue.a_recreer),
        "a_supprimer": list(vue.a_supprimer),
        "vide": vue.vide,
        "resume": vue.resume(),
        "applique": vue.applique,
    }


@router.post("/checkpoints/{identifiant}/restaurer",
             summary="Remettre le workspace dans l'état du point de reprise")
async def restaurer(identifiant: str, requete: RestaurerRequest) -> dict:
    """Destructif, et traité comme tel.

    Un refus rend `200` avec `restaure: false` et son verdict : au niveau
    d'autonomie livré c'est l'issue **attendue** — Aegis vient de déposer
    une demande d'accord — et non une faute.
    """
    try:
        reprise = _checkpoint.restaurer(_aegis(), identifiant,
                                        project_id=requete.project_id)
    except _checkpoint.CheckpointIntrouvable as exc:
        raise _introuvable(identifiant) from exc
    except _checkpoint.CheckpointImpossible as exc:
        if exc.verdict:
            return {
                "restaure": False,
                "checkpoint": identifiant,
                "verdict": exc.verdict,
                "motif": exc.motif,
                # L'accord est déposé dans la file d'Aegis, pas ici. Le
                # dire explicitement : sans cette ligne, un opérateur lit
                # « refusé » et cesse d'essayer, alors que le geste
                # attendu de lui est d'aller décider.
                "accord_a_decider": exc.verdict == "require_human_validation",
                "a_restaurer": [], "a_recreer": [], "a_supprimer": [],
                "etat_repris": False, "etat_non_repris": "",
            }
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "restaure": True,
        "checkpoint": reprise.checkpoint,
        "workspace": reprise.workspace,
        "verdict": "allow",
        "motif": "",
        "accord_a_decider": False,
        "a_restaurer": list(reprise.a_restaurer),
        "a_recreer": list(reprise.a_recreer),
        "a_supprimer": list(reprise.a_supprimer),
        # Le couple. Un point de reprise sans état de mission ne ramène
        # que la moitié, et le taire ferait compter sur l'autre (HOS-223).
        "etat_repris": reprise.etat_repris,
        "etat_non_repris": reprise.etat_non_repris,
        "resume": reprise.resume(),
    }
