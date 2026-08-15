"""Ce que la mission avait annoncé écrire, confronté au disque (HOS-122).

Mesuré sur l'essai Skills360, troisième lancement : sept tâches, `7/7`,
`success: True` — et deux fichiers de tests portant le même nom de base,
dont l'un appelait `User("user_001", "auth_uid_123")` face à un
`User.__init__` qui exige un `email`. Il avait été écrit sans jamais lire
le module qu'il teste.

Le manifeste (`MissionNode.expected_outputs`) fait déclarer à chaque tâche
les fichiers dont elle a la charge, et ce module vérifie ce qu'il en est
advenu. Sans cette moitié-là, le manifeste serait une intention : le modèle
lirait « ton fichier est `identity_model.py` », en écrirait un autre, et
personne ne le saurait.

## Trois états, comme partout ailleurs ici

* **non déclaré** — aucune tâche n'a nommé de livrable. Le planificateur
  n'en a pas produit, et on ne conclut rien : ni succès, ni échec.
* **tenu** — tout ce qui était annoncé est sur le disque.
* **manquant** — au moins un fichier annoncé n'existe pas.

## Ce que ce module ne fait pas

Il ne juge pas les fichiers **non déclarés**. Une tâche qui écrit un
`conftest.py` dont personne n'avait parlé fait probablement bien son
travail. Les signaler comme des fautes fabriquerait des faux échecs, et
cinq des huit défauts de mesure de ce dépôt étaient des échecs imaginaires.

Il ne dit pas non plus qu'un fichier présent est *correct* : c'est le
travail des tests du livrable (`verification.py`). Ici on répond à une
seule question — « ce qui avait été annoncé existe-t-il ? ».
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

#: Assez pour nommer ce qui manque sans noyer le rapport. Au-delà, le
#: verdict compte plus que la liste.
_MAX_CITES = 12


def verdict(mission: Any, workspace: Optional[str]) -> Optional[dict]:
    """L'état du manifeste de cette mission, ou `None`.

    `None` veut dire « rien à confronter » — pas de workspace, ou aucune
    tâche n'a déclaré de livrable. C'est un troisième état, pas un succès.
    """
    if not workspace:
        return None
    try:
        racine = Path(workspace).expanduser().resolve()
    except OSError:
        return None
    if not racine.is_dir():
        return None

    attendus: list[str] = []
    for noeud in getattr(mission, "nodes", None) or []:
        for chemin in getattr(noeud, "expected_outputs", None) or []:
            if chemin not in attendus:
                attendus.append(chemin)
    if not attendus:
        return None

    manquants = [chemin for chemin in attendus
                 if not (racine / chemin).exists()]
    return {
        "declares": len(attendus),
        "manquants": manquants[:_MAX_CITES],
        "nombre_manquants": len(manquants),
        "tenu": not manquants,
    }


def contredit(verdict_manifeste: Optional[dict]) -> bool:
    """Un succès annoncé est-il démenti par le manifeste ?

    Seul le cas « déclaré et absent » compte. « Pas de manifeste » ne
    contredit rien : c'est une absence de mesure, et la confondre avec un
    échec est exactement le défaut symétrique de celui qu'on corrige.
    """
    return bool(verdict_manifeste) and bool(verdict_manifeste.get("manquants"))
