#!/usr/bin/env python
"""Garde-fou : les commandes de l'agent ne visent pas hors du workspace.

Branché sur le hook `pre_tool_call` de Hermes Agent. Reçoit l'appel d'outil
en JSON sur l'entrée standard, rend `{"action": "block", "message": ...}`
pour le refuser, ou rien pour le laisser passer.

## L'incident qui l'a motivé

Mesuré le 2026-08-21. La frontière du client ACP a refusé **trois fois** une
écriture hors du workspace. L'agent a alors répondu, mot pour mot :

    The write was blocked by the ACP client.
    Let me try using the terminal directly.

et le fichier est apparu hors du workspace. `session/request_permission` ne
porte que sur les éditions de fichiers ; le terminal, lui, ne demande aucune
permission — il exécute. Refuser côté client détournait donc l'agent vers un
chemin non gardé, sans rien empêcher.

Ce n'est pas propre au harnais : le mode jetable donnait déjà le même
terminal à l'agent.

## Ce que ce garde-fou vaut, et ce qu'il ne vaut pas

Il **attrape les erreurs franches** : un chemin absolu qui désigne un
ailleurs, dans une commande ou dans un argument d'outil. C'est le cas réel —
un modèle qui interprète mal « le répertoire courant » et vise le profil
utilisateur.

Il **n'arrête pas qui cherche à sortir**. Une variable shell, une
substitution `$(...)`, un `cd` préalable, un chemin relatif assez long : rien
de tout cela ne se lit dans une chaîne de commande sans exécuter un
interpréteur. Prétendre le contraire donnerait une fausse assurance, ce qui
est pire que pas de garde du tout.

**La seule contrainte réelle est un backend d'exécution isolé** —
`terminal.backend: docker` dans la configuration de l'agent. Docker est
installé sur cette machine mais son démon ne tourne pas ; l'activer est une
décision d'exploitation, pas un défaut de code.

## Pourquoi il vit dans le dépôt

La configuration de l'agent n'est pas versionnée. Les recettes de modèles
avaient déjà disparu de cette façon (HOS-140), et il a fallu les reconstruire
par recherche. Ce fichier est versionné ; `config.yaml` ne fait que le
pointer.
"""
from __future__ import annotations

import io
import json
import ntpath
import os
import re
import sys

#: Le workspace confié, posé par `lanceur_agent.py` au démarrage. Absent, ce
#: garde-fou se tait : sans référence, tout chemin est également suspect, et
#: bloquer au hasard casserait le travail légitime.
VARIABLE = "HERMES_OS_WORKSPACE"

#: Les outils dont un argument peut désigner un fichier. `terminal` est le
#: seul chemin d'évasion mesuré, mais les autres exécutent aussi.
OUTILS_SURVEILLES = {"terminal", "execute_code", "run_command", "bash", "shell"}

#: `C:\...`, `C:/...`, `\\serveur\partage`, `/c/...` (Git Bash). Une seule
#: lettre pour la forme POSIX, sans quoi `/etc/passwd` passerait pour un
#: lecteur `E:`.
_ABSOLUS = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'|;&>]*)"          # C:\x ou C:/x
    r"|(?:\\\\[^\s\"'|;&>]+)"                    # \\serveur\partage
    r"|(?:/(?:cygdrive/|mnt/)?[A-Za-z]/[^\s\"'|;&>]*)"  # /c/x
)


def _en_windows(chemin: str) -> str:
    """Ramène une graphie POSIX de lecteur à sa forme Windows."""
    m = re.match(r"^/(?:(?:cygdrive|mnt)/)?([A-Za-z])(/.*)?$", chemin)
    if not m:
        return chemin
    return f"{m.group(1).upper()}:{(m.group(2) or '').replace('/', os.sep)}"


def _dedans(chemin: str, racine: str) -> bool:
    """Le chemin est-il sous la racine ?

    Comparaison en `normcase` : Windows est insensible à la casse, et une
    comparaison exacte laisserait passer une variante de casse du même
    dossier — défaut déjà payé cinq fois côté Hermes OS (HOS-129 à 133).
    """
    try:
        vise = ntpath.normcase(ntpath.abspath(_en_windows(chemin)))
        base = ntpath.normcase(ntpath.abspath(racine))
    except (OSError, ValueError):
        return False
    return vise == base or vise.startswith(base + os.sep)


def chemins_suspects(texte: str, racine: str) -> list[str]:
    """Les chemins absolus de `texte` qui sortent de `racine`."""
    return [c for c in _ABSOLUS.findall(texte or "") if not _dedans(c, racine)]


def _arguments(charge: dict) -> dict | None:
    """Les arguments de l'appel, quelle que soit la clé qui les porte.

    Hermes Agent sérialise la charge du hook au format Claude-Code : les
    arguments arrivent sous **`tool_input`**, pas sous `args`. Ne lire
    qu'`args` rendait donc systématiquement `None`, et le garde autorisait
    tout en silence.

    Le pire est que les premiers tests passaient : ils construisaient la
    charge avec `args`, c'est-à-dire un format que rien n'émet. Ils
    mesuraient l'idée qu'on se faisait du contrat, pas le contrat. Les deux
    clés sont désormais acceptées, et le test porte sur la trame réelle.
    """
    for cle in ("tool_input", "args"):
        valeur = charge.get(cle)
        if isinstance(valeur, dict):
            return valeur
    return None


def verdict(charge: dict, racine: str) -> dict | None:
    """`{"action": "block", ...}` s'il faut refuser, sinon `None`."""
    if not racine:
        return None
    if str(charge.get("tool_name") or "") not in OUTILS_SURVEILLES:
        return None

    args = _arguments(charge)
    if not isinstance(args, dict):
        return None
    # Tous les arguments texte, pas seulement `command` : les outils
    # d'exécution n'ont pas tous le même nom de paramètre, et n'en surveiller
    # qu'un laisserait les autres passer sans que rien ne le dise.
    suspects: list[str] = []
    for valeur in args.values():
        if isinstance(valeur, str):
            suspects.extend(chemins_suspects(valeur, racine))
    if not suspects:
        return None
    return {
        "action": "block",
        "message": (
            f"Refusé par Hermes OS : cette commande vise "
            f"{', '.join(sorted(set(suspects))[:3])}, hors du workspace "
            f"confié ({racine}). Travaille dans le workspace, avec des "
            f"chemins relatifs."
        ),
    }


#: Ou le garde note ce qu'il a refuse. Un garde-fou muet ne se distingue pas
#: d'un garde-fou absent — c'est exactement ce qui a laisse le hook precedent
#: pointer six mois vers un dossier disparu sans que personne ne le voie.
JOURNAL = "garde_workspace.log"


def _noter(ligne: str) -> None:
    """Trace le refus, au mieux et sans jamais lever.

    Sous `HERMES_DATA_DIR` quand il existe — le meme dossier que le reste
    de l'etat de Hermes OS —, sinon a cote de ce script.
    """
    try:
        from datetime import datetime, timezone

        base = os.environ.get("HERMES_DATA_DIR") or os.path.dirname(
            os.path.abspath(__file__))
        horodatage = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        with io.open(os.path.join(base, JOURNAL), "a",
                     encoding="utf-8") as sortie:
            sortie.write(f"{horodatage} {ligne}" + chr(10))
    except Exception:
        pass


def main() -> int:
    try:
        charge = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        # Un garde-fou qui plante ne doit pas bloquer l'agent : il se tait.
        # Le choix inverse — refuser par défaut — transformerait la moindre
        # anomalie de plomberie en panne totale des missions.
        return 0

    racine = os.environ.get(VARIABLE, "")
    outil = charge.get("tool_name") if isinstance(charge, dict) else None

    if not racine and outil in OUTILS_SURVEILLES:
        # Le garde est invoque mais n'a **aucune reference** : il laisse
        # tout passer. C'est le pire etat possible — une protection qui
        # parait en place et ne protege rien — donc il le dit, toujours.
        _noter(f"SANS REFERENCE outil={outil!r} : {VARIABLE} absent, "
               f"rien n'est verifie")

    if os.environ.get("HERMES_GARDE_VERBEUX", "").strip() == "1":
        # Diagnostic : sans cela, un garde qui n'est jamais invoque est
        # indiscernable d'un garde qui autorise tout.
        _noter(f"VU outil={outil!r} racine={racine!r} "
               f"args={_arguments(charge if isinstance(charge, dict) else {})!r}"[:900])

    reponse = verdict(charge if isinstance(charge, dict) else {}, racine)
    if reponse is not None:
        _noter(f"REFUS outil={charge.get('tool_name')!r} "
               f"session={charge.get('session_id')!r} :: {reponse['message']}")
        sys.stdout.write(json.dumps(reponse, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
