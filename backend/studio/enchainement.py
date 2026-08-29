"""Donner à un plan l'image d'où il repart (HOS-211).

## Le problème que ça résout

`plan_video(image_depart=...)` sait partir d'une image, et `LoadImage` ne
sait lire qu'un seul dossier : le `input` de ComfyUI. Tout ce qui est
produit ailleurs — une image SDXL, un plan vidéo — est écrit dans le
dossier de **sortie**, `E:\\YouTube\\Generations`.

Il manquait donc le pont. Chaque « SDXL → vidéo LTX » du cahier des
charges butait dessus, et l'enchaînement d'un plan sur le précédent
n'existait qu'à moitié : `/studio/last-frame` savait extraire une image
d'une vidéo, rien ne savait déposer une image déjà faite.

## Pourquoi une seule fonction pour les deux

Un plan qui repart d'un autre ne devrait pas avoir à savoir si son
prédécesseur a produit une vidéo ou une image fixe. `preparer_depart()`
regarde le fichier et fait ce qu'il faut. La file de nuit s'en sert sans
rien connaître de ffmpeg, et l'écran s'en sert par la route.

## Ce qui n'est jamais supposé

Une extraction est vérifiée **sur le disque**. `ffmpeg` rend 0 dans des
cas où il n'a rien écrit — c'est consigné dans `montage.py`, et un
départ manquant ne se verrait pas : le plan repartirait du bruit, sans
erreur, et la continuité serait perdue en silence. C'est exactement le
défaut qu'une vidéo assemblée révèle trop tard.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger("hermes_os.studio.enchainement")

#: Où ComfyUI lit les images d'entrée. C'est le seul dossier que
#: `LoadImage` sait nommer, donc le seul endroit où déposer une image de
#: départ. L'installation est fixe sur cette machine et un chemin lisible
#: vaut mieux qu'une déduction qui échoue en silence.
DOSSIER_ENTREE_COMFY = (
    r"C:\AI\Apps\ComfyUI-ROCm\comfyui-rocm-091926\input")

#: Ce que `preparer_depart` accepte comme source vidéo, et ce qu'il traite
#: comme image déjà faite. Une extension inconnue est refusée plutôt que
#: devinée : copier un fichier illisible produirait un `LoadImage` qui
#: échoue au milieu d'une nuit.
VIDEOS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


class DepartImpossible(RuntimeError):
    """Aucune image de départ n'a pu être préparée, et on dit pourquoi."""


def _nom_sur(source: str, nom: Optional[str]) -> str:
    if not nom:
        nom = "depart_" + os.path.splitext(os.path.basename(source))[0]
    if not nom.lower().endswith(".png"):
        nom += ".png"
    # Le nom vient de l'appelant : n'en garder que le nom de fichier, pour
    # qu'un « ../.. » n'écrive pas hors du dossier d'entrée.
    return os.path.basename(nom)


def preparer_depart(source: str, nom: Optional[str] = None, *,
                    dossier: str = DOSSIER_ENTREE_COMFY,
                    largeur: Optional[int] = None,
                    hauteur: Optional[int] = None) -> str:
    """Rendre le nom que `plan_video(image_depart=...)` attend.

    Une vidéo donne sa dernière image ; une image est copiée. Lève
    `DepartImpossible` plutôt que de rendre un nom qui ne chargerait pas —
    un plan qui repart du bruit au lieu de son prédécesseur produit un
    rendu parfaitement valide et une continuité perdue.

    `largeur`/`hauteur` recadrent l'image au rapport visé avant de la
    mettre à l'échelle. Ce n'est pas un confort : `LTXVImgToVideo` reçoit
    les dimensions du plan et **redimensionne sans recadrer**. Une image
    SDXL en 768 × 1344 (rapport 0,571) donnée à un plan en 704 × 1280
    (0,550) serait donc **étirée** — visible sur un visage, et rien ne le
    dirait. Le recadrage est centré et coûte 3,8 % de champ latéral.

    Sans ces deux valeurs, l'image passe telle quelle : une image déjà au
    bon format n'a rien à y gagner.
    """
    if not source or not os.path.isfile(source):
        raise DepartImpossible(f"introuvable : {source}")

    extension = os.path.splitext(source)[1].lower()
    cible = os.path.join(dossier, _nom_sur(source, nom))
    os.makedirs(dossier, exist_ok=True)

    if extension in IMAGES:
        if largeur and hauteur:
            _recadrer(source, cible, int(largeur), int(hauteur))
        else:
            shutil.copyfile(source, cible)
    elif extension in VIDEOS:
        _derniere_image(source, cible)
        if largeur and hauteur:
            _recadrer(cible, cible, int(largeur), int(hauteur))
    else:
        raise DepartImpossible(
            f"extension inconnue : {extension!r} — attendues "
            f"{sorted(VIDEOS | IMAGES)}")

    # Vérifié sur le disque, jamais d'après un code de retour.
    if not os.path.isfile(cible) or not os.path.getsize(cible):
        raise DepartImpossible(f"rien n'a été écrit dans {cible}")
    logger.info("depart prepare : %s -> %s", source, cible)
    return os.path.basename(cible)


def _recadrer(source: str, cible: str, largeur: int, hauteur: int) -> None:
    """Recadrer au rapport visé, puis mettre à l'échelle.

    `increase` remplit le cadre en débordant, `crop` reprend le centre :
    l'image couvre donc toute la surface sans jamais être déformée. Une
    image déjà au bon rapport traverse ces deux filtres sans changer.
    """
    from backend.studio.relecteur import ffmpeg

    ff = ffmpeg()
    if not ff:
        raise DepartImpossible("ffmpeg introuvable — recadrage impossible")

    provisoire = cible + ".recadre.png"
    p = subprocess.run(
        [ff, "-v", "error", "-i", source, "-vf",
         f"scale={largeur}:{hauteur}:force_original_aspect_ratio=increase"
         f":flags=lanczos,crop={largeur}:{hauteur}",
         "-frames:v", "1", "-y", provisoire],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180)
    if not os.path.isfile(provisoire) or not os.path.getsize(provisoire):
        raise DepartImpossible(
            (p.stderr or "recadrage sans résultat").strip()[:400])
    os.replace(provisoire, cible)


def _derniere_image(source: str, cible: str) -> None:
    from backend.studio.relecteur import ffmpeg

    ff = ffmpeg()
    if not ff:
        raise DepartImpossible("ffmpeg introuvable")

    # `-sseof -0.1` : se placer un dixième de seconde avant la fin plutôt
    # que de décoder tout le plan pour n'en garder que la dernière image.
    p = subprocess.run([ff, "-v", "error", "-sseof", "-0.1", "-i", source,
                        "-vframes", "1", "-y", cible],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    if not os.path.isfile(cible) or not os.path.getsize(cible):
        raise DepartImpossible(
            (p.stderr or "aucune image extraite").strip()[:400])


__all__ = ["DOSSIER_ENTREE_COMFY", "DepartImpossible", "IMAGES", "VIDEOS",
           "preparer_depart"]
