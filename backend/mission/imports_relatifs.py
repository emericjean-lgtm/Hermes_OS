"""Un import relatif qui remonte au-dessus de son paquet (HOS-146).

Mesuré le 2026-08-21, section §9 d'un déroulé de cahier, sur les deux
passes. Le livrable contenait `tests/test_atelier.py` :

    from django.test import TestCase
    from ..models import Atelier

et la collecte échouait avant le premier test :

    ImportError: attempted relative import beyond top-level package

Aucun instrument ne le voyait. La porte de syntaxe (HOS-121) compile le
fichier sans broncher — il est syntaxiquement parfait. La détection de
symboles (HOS-135) ne suit pas les imports. `imports_locaux` (HOS-124)
cherche des **boucles**, ce qui est une autre question. Le verdict des
tests l'a bien attrapé, mais après coup : la section était déjà consommée,
et c'est lui qui a arrêté la campagne à sa cinquième section.

## La règle, et pourquoi elle est sûre

Pour un module `a/b/c.py`, Python numérote les niveaux depuis son propre
paquet : `.` vaut `a.b`, `..` vaut `a`, et `...` sortirait de l'arbre. Le
niveau maximal est donc le **nombre de dossiers** entre la racine et le
fichier.

`tests/test_atelier.py` a un seul dossier : `.` est valide, `..` ne l'est
pas. C'est exactement ce que l'interpréteur a refusé.

Cette règle ne depend d'aucune convention de projet, d'aucun `sys.path`,
d'aucun outil de test : elle est celle du langage. Un import qui la viole
échoue partout, toujours.

## Ce qu'elle ne prétend pas

Elle ne dit rien d'un import relatif **valide** qui pointerait vers un
module inexistant, ni des paquets implicites — un dossier sans
`__init__.py` peut faire échouer un import relatif pourtant conforme à la
règle ci-dessus. Signaler ces cas-là demanderait de deviner comment le
projet sera importé, et cinq des défauts de mesure de ce dépôt étaient des
échecs imaginaires. On répond à une seule question, celle qu'on peut
démontrer.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.mission.imports_relatifs")


def _profondeur(chemin: Path, racine: Path) -> Optional[int]:
    """Combien de dossiers séparent `chemin` de `racine`, ou None."""
    try:
        relatif = chemin.resolve().relative_to(racine.resolve())
    except (OSError, ValueError):
        return None
    return len(relatif.parts) - 1


def remontees_invalides(source: str, profondeur: int) -> list[tuple[int, int]]:
    """Les `(ligne, niveau)` qui remontent au-dessus du paquet.

    `profondeur` est le nombre de dossiers entre la racine du projet et le
    fichier. Un fichier à la racine ne peut porter aucun import relatif.
    """
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        # La porte de syntaxe s'en occupe ; se taire ici évite deux
        # messages pour un seul défaut.
        return []
    fautifs = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.ImportFrom) and (noeud.level or 0) > profondeur:
            fautifs.append((noeud.lineno, noeud.level))
    return fautifs


def verdict(racine: str) -> Optional[dict]:
    """Le premier import relatif invalide du projet, ou None.

    Rend un dict plutôt qu'un booléen : le message doit pouvoir nommer le
    fichier, la ligne et le niveau — « un import est invalide quelque part »
    envoie chercher partout.
    """
    base = Path(racine)
    if not base.is_dir():
        return None
    for fichier in sorted(base.rglob("*.py")):
        if any(p in {"__pycache__", ".venv", "node_modules", ".git"}
               for p in fichier.parts):
            continue
        profondeur = _profondeur(fichier, base)
        if profondeur is None:
            continue
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ligne, niveau in remontees_invalides(source, profondeur):
            return {
                "fichier": str(fichier.relative_to(base)),
                "ligne": ligne,
                "niveau": niveau,
                "profondeur": profondeur,
            }
    return None


def message(racine: str) -> str:
    """Ce qu'on dit à l'agent, ou "" s'il n'y a rien à dire."""
    faute = verdict(racine)
    if faute is None:
        return ""
    points = "." * faute["niveau"]
    return (
        f"\n\nIMPORT RELATIF INVALIDE — {faute['fichier']}:{faute['ligne']}\n"
        f"`from {points}...` remonte de {faute['niveau']} niveaux, mais ce "
        f"fichier n'en a que {faute['profondeur']} au-dessus de lui. Python "
        f"refuse : « attempted relative import beyond top-level package ».\n"
        f"Utilise un import absolu depuis la racine du projet."
    )


def message_du_fichier(chemin: str, source: str, racine: str) -> str:
    """Le meme avertissement, mais **au moment de l'ecriture**.

    `message(racine)` parcourt un projet fini ; celui-ci juge un seul
    fichier qu'on vient d'ecrire. La difference est ce qu'elle coute :
    mesure du 2026-08-21, §9 a echoue **deux fois** sur le meme import
    avant que quiconque ne le voie. Dit a l'ecriture, il se corrige au tour
    suivant, pas a la campagne suivante.

    Se tait quand le fichier n'est pas du Python, ou n'est pas sous la
    racine : un avertissement hors sujet apprend a l'agent a ignorer les
    avertissements.
    """
    cible = Path(chemin)
    if cible.suffix != ".py":
        return ""
    profondeur = _profondeur(cible, Path(racine))
    if profondeur is None:
        return ""
    fautes = remontees_invalides(source, profondeur)
    if not fautes:
        return ""
    ligne, niveau = fautes[0]
    points = "." * niveau
    saut = chr(10) * 2
    return (
        f"{saut}IMPORT RELATIF INVALIDE — ligne {ligne} : "
        f"`from {points}module import ...` remonte de {niveau} niveaux, "
        f"mais ce fichier n'en a que {profondeur} au-dessus de lui. Python "
        f"refusera : « attempted relative import beyond top-level "
        f"package ». Utilise un import absolu depuis la racine du projet."
    )
