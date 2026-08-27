"""Regarder ce qui a été rendu, et dire s'il correspond (HOS-191).

## Pourquoi ce module existe

Un rendu qui se termine sans erreur n'est pas un rendu réussi. C'est la
règle centrale de ce dépôt, et elle s'applique à la génération d'images
exactement comme à l'exécution d'une mission : cinq défauts distincts y ont
déjà produit des missions `success: True, 5/5` au-dessus d'un workspace
vide.

Un plan vidéo se termine toujours. ComfyUI rend un MP4 valide même quand le
contenu n'a rien à voir avec la consigne — et à cinq minutes de calcul par
seconde de vidéo, découvrir cela au montage coûte une nuit.

## Le piège que ce module a failli devenir

Interrogé une première fois, le modèle a répondu « matches: true,
confidence: 98 » en énumérant comme présents les trois éléments de la
consigne — dont de la vapeur que l'œil ne trouvait pas sur l'image. Un
relecteur qui approuve tout ne mesure rien : il **fabrique** de la
confiance, ce qui est pire que de n'en fabriquer aucune.

La qualification passe donc par le cas négatif. `qwen3.5-2b` a refusé les
quatre consignes fausses qu'on lui a soumises sur la même image — y compris
la plus proche, une rue de nuit en néons bleus sous la pluie, qui partage
l'ambiance sans partager le sujet — et accepté la vraie. Le banc est
`backend/tests/test_studio_relecteur.py`.

## Ne jamais borner la réponse

`num_predict` à 300 rendait `done_reason=length` et une réponse **vide** :
ce modèle dépense son budget en raisonnement, et la fenêtre se ferme avant
la conclusion. Le prendre pour un refus aurait disqualifié un modèle qui
fonctionne — le défaut exact que `CLAUDE.md` documente sous « ni un échec
sur parole ».
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.studio.relecteur")

#: Le modèle qualifié. Note de vision 83 au catalogue mesuré, 2,55 Go sur
#: le disque — même note que les 4b et 9b pour un quart de la taille.
#:
#: Le tag porte `num_ctx 16384` et non les 262144 du tag d'origine. Le
#: relecteur voit une image et cent vingt jetons de consigne : les 256k
#: réservaient un cache KV qui ne servait jamais, et dont l'allocation
#: faisait dépasser 300 s au chargement à froid — ce qui s'est lu comme un
#: relecteur en panne. Mesuré le 2026-08-27 sur le même plan : 6,29 → 2,41
#: Gio résidents, 21,7 → 5,0 s à chaud, plus de 300 → 9,9 s à froid.
MODELE_DEFAUT = "qwen3.5-2b-relecteur:latest"

QUESTION = (
    "You are checking a generated video frame against the prompt that was "
    "supposed to produce it. Report what you actually see, not what the "
    "prompt says.\n\n"
    # Sans cette règle, le verdict portait sur un seuil que la consigne ne
    # fixait pas. Sur un plan réel, deux réglages du **même** modèle ont vu
    # exactement la même chose — rue étroite, nuit, sodium, asphalte
    # mouillé, pas de vapeur — et rendu des verdicts opposés. Ce n'était pas
    # une divergence de perception mais un blanc dans la question. À cinq
    # minutes de calcul par seconde de vidéo, un plan correct rejeté pour un
    # détail d'ambiance coûte aussi cher qu'un plan faux accepté.
    "RULE: answer matches=true when the frame shows the scene the prompt "
    "describes - same subject, same setting, same time of day and lighting. "
    "A secondary detail that is absent goes in \"missing\" and does NOT by "
    "itself make it false. Answer matches=false when the subject, the "
    "setting, the time of day or the lighting is wrong.\n\n"
    "PROMPT: {consigne}\n\n"
    "Answer ONLY with JSON: {{\"matches\": true|false, \"confidence\": 0-100, "
    "\"present\": [\"...\"], \"missing\": [\"...\"], \"defects\": [\"...\"]}}"
)


@dataclass
class Verdict:
    """Ce que le relecteur a vu, ou pourquoi il n'a rien pu dire."""

    #: `None` quand la relecture n'a pas abouti. Jamais confondu avec
    #: `False` : « je n'ai pas pu regarder » n'est pas « ça ne correspond
    #: pas », et traiter les deux pareil ferait rejeter des plans corrects.
    correspond: Optional[bool] = None
    confiance: int = 0
    present: list[str] = field(default_factory=list)
    manquant: list[str] = field(default_factory=list)
    defauts: list[str] = field(default_factory=list)
    images_vues: int = 0
    raison: str = ""

    @property
    def a_pu_juger(self) -> bool:
        return self.correspond is not None


def ffmpeg() -> Optional[str]:
    """Le binaire, ou None. Cherché plutôt que supposé sur le PATH."""
    trouve = shutil.which("ffmpeg")
    if trouve:
        return trouve
    for base in (os.environ.get("LOCALAPPDATA", ""),):
        if not base:
            continue
        racine = os.path.join(base, "Microsoft", "WinGet", "Packages")
        if not os.path.isdir(racine):
            continue
        for dossier, _, fichiers in os.walk(racine):
            if "ffmpeg.exe" in fichiers:
                return os.path.join(dossier, "ffmpeg.exe")
    return None


def duree_s(video: str) -> float:
    """La durée du plan en secondes, ou 0.0 si la mesure échoue.

    Lue par ffprobe plutôt que déduite d'un nombre d'images et d'une
    cadence supposée : les plans sortent à 24 ou 25 im/s selon le graphe,
    et une déduction fausse ici décalerait toutes les extractions.
    """
    binaire = ffmpeg()
    if not binaire or not os.path.exists(video):
        return 0.0
    sonde = binaire.replace("ffmpeg.exe", "ffprobe.exe").replace(
        "ffmpeg.EXE", "ffprobe.exe")
    if not os.path.exists(sonde):
        return 0.0
    try:
        sortie = subprocess.run(
            [sonde, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        return max(0.0, float(sortie))
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


#: Où puiser dans le plan, en fraction de sa durée. Ni 0 ni 1 : un plan
#: qui ouvre ou ferme en fondu donnerait des images noires, qu'aucun
#: relecteur ne peut juger et qui condamneraient le plan à tort.
INSTANTS = (0.15, 0.50, 0.85)


def extraire(video: str, combien: int = 3) -> list[str]:
    """Quelques images réparties dans le plan.

    Trois et non une : un plan peut commencer juste et dériver. Prendre
    seulement la première image, c'est relire la couverture d'un livre.

    La première version demandait ces trois images au filtre `thumbnail`,
    qui choisit une image représentative **par lot** de cent. Un plan LTX
    en fait quarante-neuf : elle en rendait donc une seule, en silence,
    tout en documentant qu'elle en rendait trois. Le lot réduit à la
    longueur du plan n'a pas corrigé le défaut — les trois fichiers
    sortaient alors *octet pour octet identiques*, ce que seule une
    empreinte a révélé, les tailles se ressemblant déjà assez pour ne pas
    alerter.

    On demande donc chaque image à un instant précis, et une par appel :
    c'est vérifiable, et ça l'a été.
    """
    binaire = ffmpeg()
    if not binaire or not os.path.exists(video):
        return []

    combien = max(1, min(combien, len(INSTANTS)))
    duree = duree_s(video)
    if duree <= 0:
        return []

    dossier = tempfile.mkdtemp(prefix="hermes_relecture_")
    cadres: list[str] = []
    for rang, fraction in enumerate(INSTANTS[:combien], 1):
        chemin = os.path.join(dossier, f"plan_{rang:03d}.png")
        try:
            subprocess.run(
                [binaire, "-y", "-loglevel", "error",
                 # `-ss` avant `-i` : ffmpeg cherche au lieu de décoder
                 # tout le plan depuis le début, trois fois de suite.
                 "-ss", f"{duree * fraction:.3f}", "-i", video,
                 "-frames:v", "1", chemin],
                capture_output=True, timeout=120, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            logger.debug("extraction impossible à %.2f", fraction, exc_info=True)
            continue
        if os.path.exists(chemin) and os.path.getsize(chemin) > 0:
            cadres.append(chemin)

    return cadres


def _interroger(modele: str, consigne: str, image: str, url: str,
                delai: float) -> dict[str, Any]:
    from urllib import request

    with open(image, "rb") as f:
        img64 = base64.b64encode(f.read()).decode()

    corps = json.dumps({
        "model": modele,
        "prompt": QUESTION.format(consigne=consigne),
        "images": [img64],
        "stream": False,
        # Pas de `num_predict` : borné, ce modèle rend une réponse vide.
        "options": {"temperature": 0.1},
    }).encode()

    req = request.Request(f"{url.rstrip('/')}/api/generate", data=corps,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=delai) as r:
        d = json.loads(r.read().decode())

    if d.get("done_reason") == "length":
        return {"tronque": True}

    brut = (d.get("response") or "").strip()
    try:
        return json.loads(brut[brut.index("{"):brut.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {"illisible": brut[:160]}


def relire(video: str, consigne: str, *, modele: str = MODELE_DEFAUT,
           images: int = 3, url: str = "http://127.0.0.1:11434",
           delai: float = 300.0,
           interroge: Optional[Callable[..., dict]] = None) -> Verdict:
    """Le plan correspond-il à sa consigne ?

    Le verdict est **conjonctif** : une seule image qui ne correspond pas
    condamne le plan. Un plan dont le tiers dérive n'est pas utilisable, et
    une moyenne le ferait passer.
    """
    cadres = extraire(video, images)
    if not cadres:
        return Verdict(raison="aucune image n'a pu être extraite du plan")

    poser = interroge or _interroger
    v = Verdict(images_vues=0)
    accords: list[bool] = []

    for cadre in cadres:
        try:
            r = poser(modele, consigne, cadre, url, delai)
        except Exception as e:
            v.raison = f"{type(e).__name__}: {str(e)[:120]}"
            continue

        if r.get("tronque"):
            v.raison = "la fenêtre du modèle s'est fermée avant sa conclusion"
            continue
        if r.get("illisible") is not None:
            v.raison = "réponse non analysable : " + str(r["illisible"])[:80]
            continue
        if not isinstance(r.get("matches"), bool):
            v.raison = "le modèle n'a pas rendu de verdict"
            continue

        v.images_vues += 1
        accords.append(bool(r["matches"]))
        v.confiance = max(v.confiance, int(r.get("confidence") or 0))
        for cle, cible in (("present", v.present), ("missing", v.manquant),
                           ("defects", v.defauts)):
            for x in (r.get(cle) or []):
                if isinstance(x, str) and x not in cible:
                    cible.append(x)

    if not accords:
        v.raison = v.raison or "aucune image n'a pu être jugée"
        return v

    v.correspond = all(accords)
    if not v.correspond:
        v.raison = (f"{accords.count(False)} image(s) sur {len(accords)} "
                    "ne correspondent pas")
    return v
