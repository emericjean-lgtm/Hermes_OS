"""Où vit l'état de l'utilisateur — hors du dépôt (HOS-215).

## Le défaut que ça corrige

Mesuré le 2026-09-02 : `data/db` 18 Mo, `data/eventbus` 8,2 Mo,
`data/snapshots` 2,2 Mo, `data/logs`, plus `_memory_.db` à la
racine — **tout l'état vivait dans le dépôt**.

`.gitignore` le protège de git. Il ne le protège pas d'une **mise à
jour** : remplacer le répertoire de l'application, qui est la façon
normale de mettre à jour un logiciel téléchargé, efface la base, la
mémoire, le bus d'événements et les instantanés — c'est-à-dire la
capacité de reprise elle-même.

Agent OS a résolu ça en rangeant sa base sous `~/.agentic-os/` et en
publiant un « preserve set » : la liste explicite de ce qu'une mise à
jour ne touche jamais. Leur règle tient en une phrase : *mettez les
réglages hors du code, sinon ils repartent à chaque version*.

## Ce que ce module décide

Une **racine d'état unique**, résolue une fois, hors du dépôt :

1. `HERMES_DATA_DIR` s'il est posé — le dernier mot revient à l'usager ;
2. sinon `%LOCALAPPDATA%\\HermesOS` sur Windows ;
3. sinon `$XDG_DATA_HOME/hermes-os`, ou `~/.local/share/hermes-os`.

Le choix de `%LOCALAPPDATA%` plutôt que `%APPDATA%` est délibéré : cet
état est propre à la machine — bases, index vectoriels, journaux — et n'a
rien à faire dans un profil itinérant qui se synchroniserait sur le
réseau.

## Ce qu'il refuse

Une racine **à l'intérieur du dépôt** est refusée, même demandée
explicitement. C'est le défaut qu'on corrige ; le permettre par
configuration reviendrait à le laisser revenir. Les tests, eux, passent
par `tmp_path` et n'ont pas besoin de cette porte.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

#: `backend/core/etat.py` → `backend/core` → `backend` → racine du dépôt.
RACINE_DEPOT = Path(__file__).resolve().parents[2]

#: Le nom du dossier, sous la racine du système. Pas « hermes » tout
#: court : `%LOCALAPPDATA%\hermes` appartient déjà à Hermes Agent — c'est
#: son `HERMES_HOME`, avec ses profils et ses clés. Deux logiciels
#: différents dans le même dossier, c'est une mise à jour de l'un qui
#: casse l'autre.
NOM_DOSSIER = "HermesOS"

#: Les sous-dossiers que l'application possède. Énumérés plutôt que créés
#: à la volée : cette liste **est** le « preserve set » — ce qu'une mise
#: à jour ne doit jamais toucher, et ce qu'une sauvegarde doit prendre.
#: `workflows` n'y figure pas : `data/workflows/*.yaml` est **suivi par
#: git**, donc livré avec l'application. Le critère n'est pas « où c'est
#: rangé » mais **qui l'a écrit** — ce que git suit se remplace à chaque
#: mise à jour, ce que l'utilisateur produit doit lui survivre.
SOUS_DOSSIERS = ("db", "logs", "snapshots", "eventbus", "memoire", "config")


class RacineInvalide(RuntimeError):
    """La racine demandée ne peut pas accueillir l'état de l'utilisateur."""


def _racine_systeme() -> Path:
    """Le dossier de données de l'utilisateur, selon la plateforme."""
    local = os.environ.get("LOCALAPPDATA")
    if local and os.name == "nt":
        return Path(local) / NOM_DOSSIER
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "hermes-os"
    return Path.home() / ".local" / "share" / "hermes-os"


def _dans_le_depot(chemin: Path) -> bool:
    try:
        chemin.resolve().relative_to(RACINE_DEPOT)
        return True
    except ValueError:
        return False


def resoudre_racine(demandee: str | None = None) -> Path:
    """La racine d'état, vérifiée.

    `demandee` l'emporte sur l'environnement, qui l'emporte sur le défaut
    de la plateforme. Une racine qui tomberait dans le dépôt est refusée
    en nommant le défaut qu'elle recréerait.
    """
    brute = demandee or os.environ.get("HERMES_DATA_DIR")
    racine = Path(brute).expanduser() if brute else _racine_systeme()

    if _dans_le_depot(racine):
        raise RacineInvalide(
            f"la racine d'état {racine} tombe dans le dépôt ({RACINE_DEPOT}). "
            "C'est précisément le défaut corrigé par HOS-215 : une mise à "
            "jour qui remplace le répertoire de l'application effacerait la "
            "base, la mémoire et les instantanés. Posez HERMES_DATA_DIR "
            "ailleurs, ou laissez le défaut de la plateforme.")
    return racine


@lru_cache
def racine() -> Path:
    """La racine d'état du processus, créée si besoin.

    Mise en cache : une résolution par processus, pour que deux appels ne
    puissent pas répondre deux dossiers différents.
    """
    r = resoudre_racine()
    r.mkdir(parents=True, exist_ok=True)
    for nom in SOUS_DOSSIERS:
        (r / nom).mkdir(exist_ok=True)
    return r


def chemin(*parties: str) -> Path:
    """Un chemin sous la racine d'état, dossier parent créé."""
    p = racine().joinpath(*parties)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def preserve_set() -> list[Path]:
    """Ce qu'une mise à jour ne doit jamais toucher.

    Rendu comme une liste plutôt que documenté en prose : un installeur,
    une sauvegarde et un test peuvent la lire, et elle ne peut pas
    diverger de ce que le code utilise vraiment.
    """
    r = racine()
    return [r / nom for nom in SOUS_DOSSIERS]


__all__ = ["NOM_DOSSIER", "RACINE_DEPOT", "RacineInvalide", "SOUS_DOSSIERS",
           "chemin", "preserve_set", "racine", "resoudre_racine"]
