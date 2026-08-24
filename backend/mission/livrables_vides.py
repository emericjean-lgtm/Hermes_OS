r"""Un module livre qui ne contient rien (HOS-156).

## L'incident

Campagne Skill360, §8 ORGANISATION, declaree **verifiee** :

    models/atelier.py       # Atelier model placeholder
    models/employe.py       # Employe model placeholder
    models/poste.py         # Poste model placeholder
    models/responsable.py   # Responsable model placeholder

Quatre fichiers d'une ligne, et deux tests qui produisaient le vert :

    def test_import_models():       # importe un fichier ne contenant qu'un commentaire
    def test_models_files_exist():  # verifie que le fichier qu'on vient de creer existe

La verification a vu des fichiers ecrits et des tests passes, et a conclu.
Elle n'avait aucune notion de « ce fichier est un placeholder ». Le document
de conception de la section le disait pourtant sans detour : « aucune
implementation technique n'est encore ecrite ».

## Pourquoi le garde des tests tautologiques ne l'attrape pas

`tests_tautologiques` exclut deliberement les tests sans assertion, parce
que `def test_import(): import monmodule` est legitime — il echoue si
l'import leve. §8 utilise exactement cette forme legitime pour fabriquer un
vert au-dessus de quatre commentaires. Ce garde-la est correct et trop
etroit ; celui-ci prend l'autre bout du probleme.

## Ce qui est signale, et ce qui ne l'est pas

Est signale un `.py` dont le corps de module ne contient **aucune**
definition, aucune affectation et aucun import — c'est-a-dire rien qu'un
docstring, des commentaires ou `pass`. C'est demontrable a l'AST et ne
suppose rien du contenu.

Ne sont pas signales, et chacun pour une raison :

* `__init__.py` — un paquet vide est la forme normale, pas un oubli ;
* `conftest.py` — idem cote tests ;
* un module de re-export (`from .x import Y`) — il n'a rien d'autre a
  contenir ;
* un module de constantes (`X = 1`) — une affectation est du contenu.

Un fichier vide n'est pas non plus signale : il n'a jamais pretendu etre un
livrable, alors qu'un `# Atelier model placeholder` se donne pour tel.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

_TOLERES = {"__init__.py", "conftest.py", "setup.py"}

_IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".hermes",
            ".pytest_cache", "build", "dist"}

#: Ce qui compte comme du contenu. Un `Expr` isole n'y est pas : c'est un
#: docstring ou une expression sans effet, et ni l'un ni l'autre n'implemente
#: quoi que ce soit.
_CONTENU = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.Assign, ast.AnnAssign, ast.AugAssign,
            ast.Import, ast.ImportFrom,
            ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Raise,
            ast.Return, ast.Delete, ast.Assert, ast.Global)


def est_un_placeholder(source: str) -> bool:
    """Ce module se donne-t-il pour un livrable sans rien implementer ?"""
    if not source.strip():
        # Un fichier vide n'a jamais pretendu etre autre chose.
        return False
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        # Un fichier qui ne compile pas est un echec deja visible ailleurs.
        return False
    return not any(isinstance(n, _CONTENU) for n in arbre.body)


def verdict(racine: str) -> Optional[dict]:
    """Le premier module livre et vide, ou None."""
    base = Path(racine)
    if not base.is_dir():
        return None
    for fichier in sorted(base.rglob("*.py")):
        if any(p in _IGNORES for p in fichier.parts):
            continue
        if fichier.name in _TOLERES:
            continue
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if est_un_placeholder(source):
            premiere = next((l.strip() for l in source.splitlines()
                             if l.strip()), "")
            return {"fichier": str(fichier.relative_to(base)),
                    "apercu": premiere[:80]}
    return None


def message(racine: str) -> str:
    """Ce qu'on dit a l'agent, ou "" s'il n'y a rien a dire."""
    faute = verdict(racine)
    if faute is None:
        return ""
    return (
        f"\n\nLIVRABLE VIDE — {faute['fichier']}\n"
        f"Ce module ne contient ni classe, ni fonction, ni affectation : "
        f"« {faute['apercu']} ». Un fichier qui annonce un modele sans le "
        f"definir n'est pas un livrable, et les tests qui se contentent de "
        f"l'importer ne prouvent rien. Ecris ce que la section demande, ou "
        f"n'annonce pas le fichier."
    )


def message_du_fichier(chemin: str, source: str) -> str:
    """Le meme avertissement, mais **au moment de l'ecriture**."""
    nom = Path(chemin).name
    if not nom.endswith(".py") or nom in _TOLERES:
        return ""
    if not est_un_placeholder(source):
        return ""
    return (
        f"\n\nATTENTION — {nom} ne contient ni classe, ni fonction, ni "
        f"affectation. Un module qui annonce une entite sans la definir ne "
        f"vaut pas livrable : la section sera comptee comme non faite. "
        f"Ecris-le maintenant plutot que de laisser un jalon."
    )
