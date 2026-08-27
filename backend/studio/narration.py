"""La narration par la voix clonée « Michael » (HOS-195).

## D'où vient cette voix

D'un enregistrement fourni par l'utilisateur — une histoire du soir qu'il
interprète sous le personnage « Michael ». Confirmé explicitement le
2026-08-27 : c'est sa propre voix, en performance de personnage, pas
l'enregistrement d'un tiers. La référence vit sous
`C:\\AI\\Models\\Voices\\michael\\`, hors du dépôt — c'est un fichier
personnel, pas un artefact de code.

Les réglages retenus — `exaggeration 0.3`, `cfg_weight 0.3` — ne sont pas
ceux par défaut du modèle (0.5/0.5). Mesuré le 2026-08-27 sur la même
phrase : le défaut donne un débit plus appuyé, moins adapté à une
narration continue. C'est le couple documenté sous « narration » dans les
essais de qualification, et il est encodé dans `reglages.json` à côté de
la référence plutôt que deviné en silence à chaque appel.

## Pourquoi la carte est arbitrée ici aussi

Mesuré : 4,38 Gio de pic pendant la synthèse. Ce n'est pas gratuit comme
Piper (0 VRAM, CPU) — donc soumis à la même règle que les rendus : la
carte se réserve, et un rendu vidéo en cours refuse la synthèse plutôt que
de la laisser déborder en silence.

## Pourquoi un seul chargement pour plusieurs répliques

Charger le modèle coûte 9 à 27 s mesurées. Une narration compte plusieurs
phrases ; les synthétiser une par une rechargerait le modèle à chaque
appel. `synthetiser()` prend donc une **liste** de segments et un seul
sous-processus les traite tous.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("hermes_os.studio.narration")

#: L'interpréteur qui porte Chatterbox et hérite du torch ROCm de ComfyUI.
#: Absolu et jamais `sys.executable`, pour la même raison que
#: `hermes_agent_cli.py` : les deux environnements ne se substituent pas
#: l'un à l'autre.
PYTHON_CHATTERBOX = r"C:\AI\Apps\chatterbox-venv\Scripts\python.exe"

_ICI = os.path.dirname(os.path.abspath(__file__))
SCRIPT_OUVRIER = os.path.join(_ICI, "_chatterbox_worker.py")

VOIX_MICHAEL_DOSSIER = r"C:\AI\Models\Voices\michael"
VOIX_MICHAEL_REFERENCE = os.path.join(VOIX_MICHAEL_DOSSIER, "reference.wav")
VOIX_MICHAEL_REGLAGES = os.path.join(VOIX_MICHAEL_DOSSIER, "reglages.json")

#: Pic mesuré 4,38 Gio ; marge au-dessus comme pour les rendus vidéo.
BESOIN_NARRATION_OCTETS = 5_368_709_120  # 5 Gio

#: Le modèle recharge sans faute en moins de 30 s, mesuré à 8,6-27,7 s
#: selon la longueur de la référence. Trois minutes couvrent large.
MINUTES_PAR_LOT = 3.0


class ChatterboxIndisponible(RuntimeError):
    """L'environnement Chatterbox n'est pas installé sur cette machine."""


@dataclass
class SegmentNarre:
    identifiant: str
    chemin: str = ""
    duree_s: float = 0.0
    erreur: str = ""

    @property
    def reussi(self) -> bool:
        return bool(self.chemin) and not self.erreur


@dataclass
class Narration:
    segments: list[SegmentNarre] = field(default_factory=list)
    appareil: str = ""
    charge_s: float = 0.0
    erreur: str = ""

    @property
    def reussie(self) -> bool:
        return not self.erreur and all(s.reussi for s in self.segments)


def voix_michael_disponible() -> bool:
    return (os.path.exists(PYTHON_CHATTERBOX)
            and os.path.exists(SCRIPT_OUVRIER)
            and os.path.exists(VOIX_MICHAEL_REFERENCE))


def _reglages_michael() -> dict[str, Any]:
    try:
        with open(VOIX_MICHAEL_REGLAGES, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # Les valeurs du modèle, pas les nôtres : sans le fichier de
        # réglages, mieux vaut le défaut documenté que d'inventer.
        logger.warning("reglages.json illisible, defauts du modele utilises")
        return {"langue": "fr", "exaggeration": 0.5, "cfg_weight": 0.5}


def _appeler_ouvrier(requete: dict, minutes: float) -> dict:
    """Le sous-processus, isolé pour qu'un test puisse le remplacer.

    `errors="replace"` — même convention que `hermes_agent_cli.py` pour la
    même cause : huggingface_hub imprime parfois un avertissement accentué
    dans l'encodage système Windows plutôt qu'en UTF-8. Constaté une fois
    dans un thread lecteur de `subprocess`, silencieusement absorbé par
    Python cette fois-là — mais un décodage strict planterait la synthèse
    entière pour un octet de message d'avertissement, jamais pour le
    résultat qu'on lit sur stdout.
    """
    p = subprocess.run(
        [PYTHON_CHATTERBOX, SCRIPT_OUVRIER],
        input=json.dumps(requete), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=minutes * 60,
    )
    sortie = (p.stdout or "").strip()
    if not sortie:
        raise RuntimeError(
            f"aucune sortie du synthétiseur (code {p.returncode}) : "
            f"{(p.stderr or '')[:400]}")
    return json.loads(sortie.splitlines()[-1])


def synthetiser(
    textes: list[tuple[str, str]],
    dossier: str,
    *,
    reference: str = VOIX_MICHAEL_REFERENCE,
    reglages: Optional[dict[str, Any]] = None,
    reserver: Optional[Any] = None,
    appeler: Optional[Any] = None,
    minutes: float = MINUTES_PAR_LOT,
) -> Narration:
    """Synthétiser plusieurs répliques avec la voix clonée.

    `textes` est une liste `(identifiant, texte)` — l'identifiant nomme le
    fichier de sortie, pour que l'appelant puisse recoller ses segments
    dans l'ordre qu'il choisit.

    `reserver` est `arbitrage.carte_reservee`, injectable pour les tests.
    Sans elle, la synthèse part sans arbitrage — ce que seul un test doit
    faire, jamais un appel réel : c'est exactement le manque que ce module
    corrige par rapport à un script isolé.
    """
    if not voix_michael_disponible() and reference == VOIX_MICHAEL_REFERENCE:
        raise ChatterboxIndisponible(
            "Chatterbox n'est pas installé, ou la référence "
            f"« Michael » est absente ({VOIX_MICHAEL_REFERENCE})")

    if not textes:
        return Narration()

    r = reglages or _reglages_michael()
    requete = {
        "segments": [{"id": i, "texte": t} for i, t in textes],
        "reference": reference, "dossier": dossier,
        "langue": r.get("langue", "fr"),
        "exaggeration": r.get("exaggeration", 0.5),
        "cfg_weight": r.get("cfg_weight", 0.5),
    }
    appel = appeler or _appeler_ouvrier

    contexte = reserver(BESOIN_NARRATION_OCTETS) if reserver else None
    try:
        if contexte is not None:
            with contexte as occ:
                if not getattr(occ, "obtenu", True):
                    return Narration(erreur=getattr(occ, "detail", "")
                                     or "la carte est déjà réservée")
                if getattr(occ, "liberation_douteuse", False):
                    return Narration(erreur=getattr(occ, "detail", "")
                                     or "VRAM insuffisante")
                brut = appel(requete, minutes)
        else:
            brut = appel(requete, minutes)
    except subprocess.TimeoutExpired:
        return Narration(erreur=f"délai dépassé ({minutes:.0f} min)")
    except (json.JSONDecodeError, RuntimeError) as e:
        return Narration(erreur=str(e)[:500])

    if "erreur" in brut and "resultats" not in brut:
        return Narration(erreur=str(brut["erreur"]))

    segments = []
    for r_ in brut.get("resultats", []):
        if "erreur" in r_:
            segments.append(SegmentNarre(identifiant=str(r_["id"]),
                                         erreur=str(r_["erreur"])))
        else:
            segments.append(SegmentNarre(
                identifiant=str(r_["id"]), chemin=str(r_["chemin"]),
                duree_s=float(r_.get("duree_s") or 0.0)))

    return Narration(segments=segments, appareil=str(brut.get("appareil", "")),
                     charge_s=float(brut.get("charge_s") or 0.0))


__all__ = ["BESOIN_NARRATION_OCTETS", "ChatterboxIndisponible", "Narration",
           "SegmentNarre", "VOIX_MICHAEL_REFERENCE", "synthetiser",
           "voix_michael_disponible"]
