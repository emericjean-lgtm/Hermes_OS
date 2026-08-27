"""Enchaîner des plans pendant la nuit, et rendre un compte au matin (HOS-191).

## Pourquoi une file, et pas un simple appel

Cinq minutes de calcul par seconde de vidéo finie — mesuré le 2026-08-27 :
vingt minutes pour quatre secondes en 704 × 1280. Un short de trente
secondes demande sept à huit plans, soit près de trois heures. La production
est donc un **atelier de nuit**, pas un outil de tâtonnement, et ce qui la
gouverne n'est pas une requête mais une file.

Le modèle existe déjà dans ce dépôt : `scripts/derouler_cahier.py` déroule
un cahier des charges section par section, reprend là où il s'était arrêté,
et rend un verdict par section plutôt qu'un succès global. Les mêmes règles
valent ici, pour les mêmes raisons.

## Les trois choses qu'elle refuse de faire

**Elle ne compte pas un plan comme réussi parce qu'il s'est terminé.**
ComfyUI rend un MP4 valide même quand le contenu n'a rien à voir avec la
consigne. Chaque plan passe par le relecteur, et un plan non relu est
`indetermine` — jamais `reussi`.

**Elle ne lance rien sans la carte.** Un rendu démarré pendant qu'une
mission tient les 16 Gio ne produit pas une erreur : il produit dix-sept
fois le temps, en mémoire système, sans que rien ne le dise. La file passe
par `arbitrage.carte_reservee`.

**Elle ne perd pas la nuit sur un défaut répété.** Trois échecs consécutifs
arrêtent la file : au-delà, ce n'est plus un aléa, et continuer coûterait
huit heures pour confirmer ce que le troisième échec disait déjà.
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("hermes_os.studio.file")

#: Au-delà, ce n'est plus un aléa. Trois et non un : un échec isolé arrive
#: (un binaire absent, une seconde de contention), trois de suite décrivent
#: un défaut qui ne se réparera pas tout seul pendant la nuit.
ECHECS_AVANT_ARRET = 3


class Etat(str, Enum):
    EN_ATTENTE = "en_attente"
    RENDU = "rendu"
    #: Rendu **et** relu conforme. Le seul état qui vaut une réussite.
    RETENU = "retenu"
    #: Rendu, relu, et le relecteur a dit non.
    REJETE = "rejete"
    #: Rendu, mais pas relu — Ollama absent, fenêtre fermée, ffmpeg manquant.
    #: Distinct de `retenu` **et** de `rejete` : on ne sait pas.
    INDETERMINE = "indetermine"
    ECHOUE = "echoue"
    ABANDONNE = "abandonne"


@dataclass
class Plan:
    """Un plan à rendre, et ce qu'il est devenu."""

    identifiant: str
    consigne: str
    graphe: dict[str, Any]
    etat: Etat = Etat.EN_ATTENTE
    fichiers: list[str] = field(default_factory=list)
    duree_s: float = 0.0
    pic_vram_octets: int = 0
    confiance: int = 0
    defauts: list[str] = field(default_factory=list)
    raison: str = ""


@dataclass
class Rapport:
    """Ce qu'on lit au matin."""

    debut: float
    fin: float = 0.0
    plans: list[Plan] = field(default_factory=list)
    arret_anticipe: str = ""

    @property
    def duree_s(self) -> float:
        return round((self.fin or time.time()) - self.debut, 1)

    def compte(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for p in self.plans:
            c[p.etat.value] = c.get(p.etat.value, 0) + 1
        return c

    def resume(self) -> str:
        c = self.compte()
        retenus = c.get(Etat.RETENU.value, 0)
        return (f"{retenus}/{len(self.plans)} plan(s) retenu(s) en "
                f"{self.duree_s / 60:.0f} min — " + json.dumps(c))


def derouler(
    plans: list[Plan],
    *,
    soumettre: Callable[[dict], str],
    attendre: Callable[[str], Any],
    relire: Optional[Callable[[str, str], Any]] = None,
    reserver: Optional[Callable[[int], Any]] = None,
    besoin_octets: int = 11_525_623_808,
    journal: Optional[str] = None,
) -> Rapport:
    """Rendre chaque plan, le relire, et consigner.

    Toutes les dépendances sont injectées : la file doit être éprouvable
    sans GPU, sans ComfyUI et sans Ollama, sinon elle ne serait testée que
    par des nuits entières — et c'est précisément le genre de code qu'on
    ne teste alors jamais.

    `reserver` rend un **gestionnaire de contexte** — la signature de
    `arbitrage.carte_reservee`, à laquelle il se branche directement. La
    réservation couvre le rendu et s'arrête là : la relecture charge un
    modèle de 2,5 Gio à côté des 7,6 que ComfyUI garde résidents, ce qui
    tient dans la carte, et la tenir plus longtemps empêcherait une
    mission de reprendre la main entre deux plans.

    `journal` écrit le rapport après **chaque** plan, pas à la fin : une
    nuit interrompue à la sixième heure doit laisser une trace des cinq
    premières.
    """
    rapport = Rapport(debut=time.time())
    rapport.plans = list(plans)
    echecs = 0

    for plan in rapport.plans:
        if echecs >= ECHECS_AVANT_ARRET:
            plan.etat = Etat.ABANDONNE
            plan.raison = f"{echecs} échecs consécutifs avant ce plan"
            continue

        garde = reserver(besoin_octets) if reserver is not None else nullcontext(None)
        try:
            with garde as occupation:
                if not _carte_utilisable(plan, occupation):
                    echecs += 1
                    _consigner(journal, rapport)
                    continue

                identifiant = soumettre(plan.graphe)
                rendu = attendre(identifiant)

                plan.duree_s = float(getattr(rendu, "duree_s", 0.0))
                plan.pic_vram_octets = int(getattr(rendu, "pic_vram_octets", 0))
                plan.fichiers = list(getattr(rendu, "fichiers", []) or [])

                if not getattr(rendu, "acheve", False) or not plan.fichiers:
                    plan.etat = Etat.ECHOUE
                    plan.raison = (getattr(rendu, "erreur", "")
                                   or "aucun fichier produit")
                    echecs += 1
                    _consigner(journal, rapport)
                    continue

                plan.etat = Etat.RENDU
                echecs = 0

        except Exception as e:
            plan.etat = Etat.ECHOUE
            plan.raison = f"{type(e).__name__}: {str(e)[:160]}"
            echecs += 1
            _consigner(journal, rapport)
            continue

        _relire_le_plan(plan, relire)
        _consigner(journal, rapport)

    rapport.fin = time.time()
    if echecs >= ECHECS_AVANT_ARRET:
        rapport.arret_anticipe = (
            f"{echecs} échecs consécutifs — la file s'est arrêtée plutôt que "
            "de passer la nuit à confirmer le même défaut")
    _consigner(journal, rapport)
    return rapport


def _carte_utilisable(plan: Plan, occupation: Any) -> bool:
    """La carte est-elle réellement disponible pour ce plan ?

    Renvoie faux **et** renseigne le plan, pour que l'appelant n'ait pas à
    dupliquer le motif. Refuser un rendu vaut mieux que le lancer en
    débordement : il aboutirait, dix-sept fois plus lentement, et la nuit
    y passerait pour trois plans au lieu de dix.
    """
    if occupation is None:
        return True
    if not getattr(occupation, "obtenu", True):
        plan.etat = Etat.ECHOUE
        plan.raison = getattr(occupation, "detail", "") or "la carte est déjà réservée"
        return False
    if getattr(occupation, "liberation_douteuse", False):
        plan.etat = Etat.ECHOUE
        plan.raison = getattr(occupation, "detail", "") or "VRAM insuffisante"
        return False
    return True


def _relire_le_plan(plan: Plan, relire: Optional[Callable[[str, str], Any]]) -> None:
    """Confronter le fichier rendu à sa consigne.

    Un plan non relu reste `indetermine`. Le compter comme réussi serait
    exactement le `success: True` au-dessus d'un workspace vide que ce
    dépôt a déjà payé cinq fois.
    """
    if relire is None:
        plan.etat = Etat.INDETERMINE
        plan.raison = "aucun relecteur fourni"
        return

    if not plan.consigne.strip():
        # Sans consigne il n'y a rien à quoi comparer. Interroger quand
        # même reviendrait à demander au modèle de juger une image contre
        # une invite vide : il répondrait, et sa réponse ne voudrait rien
        # dire — le pire des deux cas, puisqu'elle porterait une
        # confiance.
        plan.etat = Etat.INDETERMINE
        plan.raison = "aucune consigne : rien à quoi comparer le plan"
        return

    try:
        v = relire(plan.fichiers[0], plan.consigne)
    except Exception as e:
        plan.etat = Etat.INDETERMINE
        plan.raison = f"relecture impossible — {type(e).__name__}"
        return

    plan.confiance = int(getattr(v, "confiance", 0))
    plan.defauts = list(getattr(v, "defauts", []) or [])
    correspond = getattr(v, "correspond", None)

    if correspond is True:
        plan.etat = Etat.RETENU
    elif correspond is False:
        plan.etat = Etat.REJETE
        plan.raison = getattr(v, "raison", "") or "ne correspond pas à la consigne"
    else:
        # Ni retenu ni rejeté : le relecteur n'a pas pu conclure, et le
        # dire vaut mieux que de trancher à sa place.
        plan.etat = Etat.INDETERMINE
        plan.raison = getattr(v, "raison", "") or "relecture non concluante"


def atelier(
    plans: list[Plan],
    *,
    base_comfy: str = "http://127.0.0.1:8188",
    minutes_par_plan: float = 45.0,
    besoin_octets: int = 11_525_623_808,
    attente_carte_s: float = 900.0,
    journal: Optional[str] = None,
) -> Rapport:
    """La file de nuit branchée sur la vraie machine.

    C'est le seul endroit qui connaisse ComfyUI, l'arbitrage et le
    relecteur à la fois ; `derouler` n'en sait rien et reste éprouvable
    sans eux.

    `attente_carte_s` vaut quinze minutes et non zéro : un travail de nuit
    peut patienter derrière une mission, là où une requête d'interface
    doit renoncer tout de suite.
    """
    from backend.studio.arbitrage import carte_reservee, pic_gpu_du_processus
    from backend.studio.comfyui import ComfyUI, pid_du_serveur
    from backend.studio.relecteur import relire

    comfy = ComfyUI(base_comfy)
    pid = pid_du_serveur()
    if pid is None:
        logger.warning(
            "processus ComfyUI introuvable : les pics de VRAM ne seront pas "
            "mesurés. Un rendu qui déborde passera alors pour un rendu lent.")

    sonde = (lambda: pic_gpu_du_processus(pid)) if pid else None

    return derouler(
        plans,
        soumettre=comfy.soumettre,
        attendre=lambda i: comfy.attendre(
            i, minutes=minutes_par_plan, sonde_vram=sonde),
        relire=lambda fichier, consigne: relire(fichier, consigne),
        reserver=lambda besoin: carte_reservee(
            besoin, attente_max_s=attente_carte_s),
        besoin_octets=besoin_octets,
        journal=journal,
    )


def _consigner(chemin: Optional[str], rapport: Rapport) -> None:
    """Écrire le rapport, sans jamais faire échouer la file pour autant."""
    if not chemin:
        return
    try:
        os.makedirs(os.path.dirname(chemin) or ".", exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(
                {"debut": rapport.debut, "fin": rapport.fin,
                 "duree_s": rapport.duree_s,
                 "arret_anticipe": rapport.arret_anticipe,
                 "compte": rapport.compte(),
                 "plans": [{**asdict(p), "etat": p.etat.value}
                           for p in rapport.plans]},
                f, ensure_ascii=False, indent=2)
    except OSError:
        logger.debug("journal de nuit non écrit", exc_info=True)
