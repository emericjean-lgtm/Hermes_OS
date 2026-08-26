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

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.voice.locale import fournisseurs
from backend.voice.preferences import Preferences, ecrire, lire, rapport

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


@router.post("/speak")
def parler(payload: dict = Body(...)) -> Response:
    """Synthétiser un texte en WAV, avec la voix locale.

    Le navigateur sait déjà parler ; cette route existe pour les cas où il
    ne peut pas — un navigateur sans voix installée, ou une lecture
    déclenchée côté serveur. Elle rend le WAV directement plutôt qu'un
    chemin : écrire un fichier pour le relire aussitôt ajouterait une
    écriture disque par phrase.
    """
    texte = str((payload or {}).get("texte") or "").strip()
    if not texte:
        raise HTTPException(status_code=422, detail="texte vide")

    fournisseur = fournisseurs()["synthese"]
    if not fournisseur.is_available():
        raise HTTPException(
            status_code=503,
            detail="aucune voix locale installée — voir /voice/state")
    return Response(content=fournisseur.synthesize(texte),
                    media_type="audio/wav")


@router.post("/transcribe")
async def transcrire(fichier: UploadFile = File(...)) -> dict:
    """Transcrire un audio téléversé.

    `faster-whisper` lit un fichier, pas un flux : l'audio est donc écrit
    dans un temporaire puis effacé. C'est une écriture par transcription,
    assumée — la seule alternative serait de réimplémenter le décodage.
    """
    fournisseur = fournisseurs()["transcription"]
    if not fournisseur.is_available():
        raise HTTPException(
            status_code=503,
            detail="transcription locale indisponible — voir /voice/state")

    octets = await fichier.read()
    if not octets:
        raise HTTPException(status_code=422, detail="fichier vide")

    suffixe = Path(fichier.filename or "audio.wav").suffix or ".wav"
    # `mkstemp` rend un descripteur **ouvert**. Le laisser tel quel verrouille
    # le fichier sous Windows et `unlink` echoue par WinError 32 — la
    # transcription reussit, et la route rend quand meme un 500.
    descripteur, chemin = tempfile.mkstemp(suffix=suffixe)
    os.close(descripteur)
    temporaire = Path(chemin)
    try:
        temporaire.write_bytes(octets)
        texte = fournisseur.transcribe(str(temporaire), lire().langue[:2])
    finally:
        temporaire.unlink(missing_ok=True)
    return {"texte": texte, "fournisseur": fournisseur.get_name()}
