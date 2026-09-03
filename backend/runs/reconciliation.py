"""Retrouver les runs dont le porteur est mort (HOS-240).

## Le défaut

`Statut.PERDU` existait dans le vocabulaire depuis HOS-221 et **rien ne
le posait**. C'est écrit noir sur blanc dans son propre CHANGELOG. Un
run dont le processus disparaît — arrêt brutal, `taskkill`, panne de
courant, exception non rattrapée qui traverse `execute_task` sans
atteindre `finalize()` — restait `en_cours` pour toujours. La console
d'opérations affichait donc des runs actifs qui ne tournaient nulle
part, et le compteur « en cours » ne redescendait jamais.

## Pourquoi pas un délai

La tentation est d'écrire « `en_cours` depuis plus de N minutes ⇒
perdu ». C'est faux dans les deux sens, et coûteux dans les deux :

- une mission longue sur un modèle local lent dépasse n'importe quel N
  raisonnable et se ferait déclarer perdue **en tournant** ;
- un processus tué à la seconde 3 resterait `en_cours` pendant N.

Un délai mesure l'impatience de l'observateur, pas la mort du porteur.

## La preuve retenue

Le seul fait qui décide vraiment est : **le processus qui a ouvert ce
run existe-t-il encore ?** Chaque run porte donc l'empreinte de son
porteur, écrite une fois à l'ouverture — `pid:date_de_démarrage`. La
date de démarrage n'est pas décorative : les PID se réutilisent, et sans
elle un nouveau processus héritant du PID d'un mort ferait passer ses
runs pour vivants.

Ce n'est pas un battement de cœur : rien n'est réécrit périodiquement.
Une écriture, à la naissance de la ligne.

## Ce qui n'est jamais posé en PERDU

- un run déjà terminal — l'invariant SQL de HOS-221 le refuserait de
  toute façon, mais on ne le lui demande même pas ;
- un run du processus **courant** — il tourne, par construction ;
- un run d'un autre processus **vivant** — deux Hermes peuvent coexister,
  et déclarer perdus les runs du voisin serait pire que le défaut ;
- un run **sans empreinte** — les lignes d'avant HOS-240. Aucune preuve
  n'est disponible : le tri-état de ce dépôt interdit de les ranger avec
  les morts. Elles sont comptées `indecidables` et signalées.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

#: Tolérance sur la date de démarrage d'un processus, en secondes. Deux
#: lectures du même processus peuvent différer de quelques microsecondes
#: selon la plateforme ; deux processus distincts ne naissent pas à la
#: même seconde avec le même PID.
TOLERANCE_S = 1.0


def empreinte_du_processus(pid: Optional[int] = None) -> str:
    """`pid:date_de_démarrage`, ou `pid:` si la date est inaccessible.

    La forme dégradée est délibérée : un PID seul vaut mieux que rien,
    et `processus_vivant` sait qu'il ne peut alors pas exclure la
    réutilisation de PID — auquel cas il refuse de conclure plutôt que
    de conclure à tort.
    """
    pid = os.getpid() if pid is None else pid
    try:
        import psutil

        return "%d:%r" % (pid, psutil.Process(pid).create_time())
    except Exception:  # pragma: no cover - psutil absent ou processus parti
        return "%d:" % pid


def processus_vivant(empreinte: str) -> Optional[bool]:
    """`True` vivant, `False` mort, `None` indécidable.

    Trois réponses et non deux : une empreinte illisible, un psutil
    absent ou un système qui refuse l'accès ne prouvent pas la mort du
    processus. Les confondre transformerait une panne d'observation en
    verdict, ce qui est exactement l'erreur que ce dépôt poursuit.
    """
    if not empreinte or ":" not in empreinte:
        return None
    tete, _, queue = empreinte.partition(":")
    try:
        pid = int(tete)
    except ValueError:
        return None

    try:
        import psutil
    except ImportError:  # pragma: no cover
        return None

    try:
        if not psutil.pid_exists(pid):
            return False
        naissance = psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:
        return False
    except Exception:  # accès refusé, /proc indisponible, …
        return None

    if not queue:
        # PID vivant, mais on ne peut pas exclure qu'il ait été réutilisé.
        return None
    try:
        attendue = float(queue)
    except ValueError:
        return None
    return abs(naissance - attendue) <= TOLERANCE_S


@dataclass
class Bilan:
    """Ce qu'une réconciliation a constaté. Trois catégories, pas deux."""

    perdus: list[str] = field(default_factory=list)
    #: Portés par un processus encore vivant — laissés strictement seuls.
    vivants: list[str] = field(default_factory=list)
    #: Aucune preuve disponible : ni vivants ni morts, et surtout pas perdus.
    indecidables: list[str] = field(default_factory=list)

    @property
    def examines(self) -> int:
        return len(self.perdus) + len(self.vivants) + len(self.indecidables)

    def to_dict(self) -> dict:
        return {"perdus": list(self.perdus), "vivants": list(self.vivants),
                "indecidables": list(self.indecidables),
                "examines": self.examines}


def reconcilier(registre=None, *, empreinte_courante: Optional[str] = None) -> Bilan:
    """Marquer perdus les runs dont le porteur a disparu.

    Idempotente par construction : `PERDU` est terminal, et l'invariant
    SQL de HOS-221 gèle **toutes** les colonnes d'un run terminal. Un
    second appel relit donc des runs déjà arrivés et ne les voit même
    plus — `non_termines()` les exclut.

    Ne lève jamais : appelée au démarrage, elle ne doit pas empêcher
    Hermes de démarrer parce qu'elle n'a pas su lire une base.
    """
    from backend.runs.registre import Cause, Registre, Statut

    bilan = Bilan()
    try:
        registre = registre if registre is not None else Registre()
        candidats = registre.non_termines()
    except Exception as erreur:  # pragma: no cover - base illisible
        logger.warning("réconciliation impossible : %s", erreur)
        return bilan

    courante = (empreinte_courante if empreinte_courante is not None
                else empreinte_du_processus())

    for run in candidats:
        try:
            empreinte = registre.processus_de(run.identifiant)
        except Exception:  # pragma: no cover
            empreinte = None

        if not empreinte:
            bilan.indecidables.append(run.identifiant)
            continue
        if empreinte == courante:
            # Le processus qui lit est celui qui l'a ouvert : il tourne.
            bilan.vivants.append(run.identifiant)
            continue

        vivant = processus_vivant(empreinte)
        if vivant is True:
            bilan.vivants.append(run.identifiant)
        elif vivant is None:
            bilan.indecidables.append(run.identifiant)
        else:
            registre.terminer(
                run.identifiant, Statut.PERDU, cause=Cause.PROCESSUS,
                raison="le processus porteur " + empreinte + " n'existe "
                       "plus ; ce qu'il avait fait avant de disparaître "
                       "n'est pas connu")
            bilan.perdus.append(run.identifiant)

    if bilan.perdus or bilan.indecidables:
        logger.info(
            "réconciliation : %d perdus, %d vivants, %d indécidables",
            len(bilan.perdus), len(bilan.vivants), len(bilan.indecidables))
    return bilan


__all__ = ["Bilan", "TOLERANCE_S", "empreinte_du_processus",
           "processus_vivant", "reconcilier"]
