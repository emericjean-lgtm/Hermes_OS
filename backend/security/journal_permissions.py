"""Ce que Hermes OS a decide quand l'agent a demande a ecrire (G-22, HOS-271).

## Le controle existait et personne ne le voyait

Sur le chemin de conversation lie a un projet, Hermes OS ouvre une session
Hermes Agent vivante par ACP. Avant chaque **edition de fichier**, l'agent
adresse au client un `session/request_permission` et **attend** ; c'est
`HermesAgentACP._repondre` qui tranche, sur la politique de Hermes OS —
hors du workspace, ou fichier gouvernant protege, refus.

Ce controle agit vraiment. Mesure du 2026-09-09, sur un tour reel : deux
demandes, **deux refus** — l'agent voulait ecrire `C:\\Users\\emeri\\NOTE.md`
alors que la session portait sur un dossier temporaire, exactement
l'incident du 2026-08-21 que le docstring de l'adaptateur decrit. Puis il a
reecrit au bon endroit.

Et pourtant : un `logger.warning`, rien d'autre. Aucune trace, aucun ecran.
Un garde-fou de securite qui agit sans temoin est un garde-fou dont
personne ne peut dire s'il agit — et une decision d'accord ne journalisait
meme pas.

## Ce que ce module fait, et ne fait pas

Il **observe**. Il ne decide rien : la decision reste dans
`HermesAgentACP._repondre`, ou elle a toujours ete. Ajouter ici une seconde
politique ferait exactement l'autorite concurrente que le contrat interdit.

Le journal est borne et vit dans le processus **qui prend ces decisions** —
le backend. Ce n'est pas la faiblesse qu'on a reprochee a
`delegation.pause` : la, l'etat vivait dans un processus ou rien ne se
passait ; ici, c'est le seul endroit ou cela se passe. La durabilite vient
du bus d'evenements, qui est le journal de Hermes OS.

## Ce que ce journal ne prouve pas

`session/request_permission` ne porte que sur les **editions de fichiers**.
Le terminal de l'agent n'en demande aucune : il execute. Un refus visible
ici ne signifie donc pas qu'une ecriture a ete empechee — l'agent peut
reessayer par le terminal, et l'a deja fait. Le journal dit ce que Hermes
OS a repondu, pas ce que l'agent a fini par faire.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Optional

logger = logging.getLogger("hermes_os.security.journal_permissions")

#: Assez pour couvrir une conversation, assez peu pour ne pas devenir une
#: memoire. Le bus d'evenements porte la trace durable ; ceci n'est qu'une
#: fenetre de lecture pour le cockpit.
TAILLE_MAX = 200

#: Les issues possibles, nommees. `refusee_hors_workspace` et
#: `refusee_protege` ne se confondent pas : la premiere dit que l'agent
#: sortait du dossier confie, la seconde qu'il touchait un fichier qui
#: definit le travail. Les fondre perdrait la seule information utile.
ACCORDEE = "accordee"
REFUSEE_HORS_WORKSPACE = "refusee_hors_workspace"
REFUSEE_PROTEGE = "refusee_protege"
SANS_OPTION = "sans_option"

_verrou = threading.Lock()
_journal: deque = deque(maxlen=TAILLE_MAX)


def consigner(*, issue: str, chemin: str, detail: str = "",
              session: str = "", workspace: str = "") -> dict[str, Any]:
    """Retient une decision et la publie au journal de Hermes OS.

    Best-effort sur la publication : une trace qui echoue ne doit pas
    empecher la decision d'etre prise — elle l'a deja ete quand on arrive
    ici, et lever ferait echouer le tour pour une raison d'observabilite.
    """
    entree = {
        "issue": issue, "chemin": chemin, "detail": detail,
        "session": session, "workspace": workspace, "quand": time.time(),
    }
    with _verrou:
        _journal.append(entree)
    _publier(entree)
    return entree


def _publier(entree: dict[str, Any]) -> None:
    topic = ("agent.permission.accordee" if entree["issue"] == ACCORDEE
             else "agent.permission.refusee")
    try:
        from backend.core.event_hub import get_event_hub

        get_event_hub().publish(topic, entree)
    except Exception:  # noqa: BLE001
        logger.debug("publication de la decision impossible", exc_info=True)


def decisions(limite: int = 50) -> dict[str, Any]:
    """Les dernieres decisions, la plus recente d'abord.

    `total` est ce que la fenetre contient, pas un decompte historique : le
    journal est borne, et presenter sa taille comme un total serait le meme
    mensonge exact que le plafond de `session.list` corrige en HOS-267.
    """
    with _verrou:
        tout = list(_journal)
    recentes = list(reversed(tout))[:limite]
    return {
        "disponible": True, "erreur": None,
        "total": len(recentes), "tronque": len(tout) > limite,
        "borne": TAILLE_MAX,
        "refus": sum(1 for e in tout if e["issue"] != ACCORDEE),
        "elements": recentes,
    }


def vider() -> None:
    """Pour les tests seulement — le journal n'a pas de purge produit."""
    with _verrou:
        _journal.clear()
