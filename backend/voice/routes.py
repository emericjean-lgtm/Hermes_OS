"""Les routes de la voix (HOS-173).

Deux verbes et rien de plus : lire l'état, l'écrire. La reconnaissance et la
synthèse vivent dans le navigateur — les faire transiter par le serveur
ajouterait un aller-retour, un format audio à négocier et une latence, pour
une capacité que le client possède déjà.

Ce que le serveur apporte : la persistance des réglages, et un rapport de
capacités qui ne ment pas.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from backend.voice.preferences import Preferences, ecrire, rapport

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/state")
def etat() -> dict[str, Any]:
    """Préférences et capacités, en un appel.

    Un seul écran les affiche ensemble ; deux routes obligeraient le client
    à orchestrer deux requêtes pour un rendu atomique.
    """
    return rapport()


@router.put("/preferences")
def enregistrer(payload: dict = Body(...)) -> dict[str, Any]:
    """Écrire les réglages, et rendre ce qui a réellement été retenu.

    Le retour porte les valeurs **bornées** : un client qui envoie un débit
    de 9 doit voir 2 revenir, plutôt que croire son réglage accepté.
    """
    connus = {c.name for c in Preferences.__dataclass_fields__.values()}
    propres = {k: v for k, v in (payload or {}).items() if k in connus}
    return {"preferences": ecrire(Preferences(**propres)).__dict__}
