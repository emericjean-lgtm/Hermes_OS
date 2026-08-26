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
from typing import Iterable, Optional

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


#: Ce qui, hors Python, trahit un livrable qui n'en est pas un.
#:
#: §27 FRONTEND a ete declaree **verifiee** — cinq livrables annonces, cinq
#: presents, tests passes — au-dessus de ceci :
#:
#:     frontend/app.js     // Frontend JS placeholder
#:                         console.log('Frontend loaded');
#:
#: Deux lignes, dont une qui se declare elle-meme comme un jalon. Le garde
#: de HOS-156 l'aurait signale sans hesiter s'il avait regarde ailleurs que
#: dans les `.py`.
#:
#: Le critere hors Python ne peut pas etre l'AST. On retient donc deux
#: signes qui ne trompent pas : un fichier dont **tout** le contenu utile
#: tient en commentaires, ou qui se declare placeholder dans ses premieres
#: lignes tout en tenant en moins de cinq lignes utiles.
_AVEUX = ("placeholder", "to be implemented", "a implementer",
          "coming soon", "tbd", "todo: implement")

_COMMENTAIRE = ("//", "/*", "*", "*/", "#", "<!--", "-->")

_EXTENSIONS_SURVEILLEES = {".js", ".jsx", ".ts", ".tsx", ".css", ".scss"}


def _lignes_utiles(source: str) -> list[str]:
    """Les lignes qui ne sont ni vides ni des commentaires."""
    utiles = []
    for brute in source.splitlines():
        ligne = brute.strip()
        if not ligne or ligne.startswith(_COMMENTAIRE):
            continue
        utiles.append(ligne)
    return utiles


def est_un_jalon_hors_python(nom: str, source: str) -> bool:
    """Ce livrable non-Python se donne-t-il pour fait sans l'etre ?

    Deliberement etroit, comme son homologue Python. Un fichier court mais
    reel — un `index.css` de dix regles — n'est pas signale : il faut qu'il
    **s'avoue** jalon, ou qu'il ne contienne rien d'autre que des
    commentaires.
    """
    if not source.strip():
        return False
    utiles = _lignes_utiles(source)
    if not utiles:
        # Rien que des commentaires : le fichier existe et ne fait rien.
        return True
    tete = " ".join(source.splitlines()[:4]).lower()
    return len(utiles) < 5 and any(aveu in tete for aveu in _AVEUX)


def verdict(racine: str,
            touches: Optional[Iterable[str]] = None) -> Optional[dict]:
    """Le premier module livre et vide, ou None.

    `touches` restreint l'examen aux fichiers que **cette** mission a crees
    ou modifies. Sans lui le garde inspectait tout le workspace, et une
    section pouvait donc etre bloquee pour un jalon laisse par une autre —
    sans aucun moyen de s'en sortir, puisqu'elle n'y touche pas.

    Le defaut n'a pas mordu la premiere fois (§9 avait bien reecrit le
    fichier qu'on lui reprochait) mais il attendait la premiere section
    innocente. Un garde qui reproche a une mission le travail d'une autre
    produit un faux echec, et ce projet a mesure que cinq de ses huit
    defauts d'instrumentation en produisaient.
    """
    base = Path(racine)
    if not base.is_dir():
        return None
    if touches is not None:
        candidats = sorted(
            c for c in (base / str(r).replace("\\", "/") for r in touches)
            if (c.suffix == ".py"
                or c.suffix.lower() in _EXTENSIONS_SURVEILLEES)
            and c.is_file())
    else:
        candidats = sorted(
            c for c in base.rglob("*")
            if c.is_file() and (c.suffix == ".py"
                                or c.suffix.lower()
                                in _EXTENSIONS_SURVEILLEES))
    for fichier in candidats:
        if any(p in _IGNORES for p in fichier.parts):
            continue
        if fichier.name in _TOLERES:
            continue
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        vide = (est_un_placeholder(source) if fichier.suffix == ".py"
                else est_un_jalon_hors_python(fichier.name, source))
        if vide:
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
        f"l'importer ne prouvent rien.\n"
        f"Deux issues, et une seule est un jalon : soit tu ecris ce "
        f"que la section demande, soit tu **supprimes le fichier**. "
        f"Si l'implementation vit ailleurs, ce module ne doit pas "
        f"exister : un stub qui annonce « rien ici » est pire que son "
        f"absence, parce qu'un import le trouvera."
    )


def message_du_fichier(chemin: str, source: str) -> str:
    """Le meme avertissement, mais **au moment de l'ecriture**."""
    nom = Path(chemin).name
    from pathlib import Path as _P

    suffixe = _P(nom).suffix.lower()
    if nom in _TOLERES:
        return ""
    if suffixe == ".py":
        if not est_un_placeholder(source):
            return ""
    elif suffixe in _EXTENSIONS_SURVEILLEES:
        if not est_un_jalon_hors_python(nom, source):
            return ""
    else:
        return ""
    return (
        f"\n\nATTENTION — {nom} ne contient ni classe, ni fonction, ni "
        f"affectation. Un module qui annonce une entite sans la definir ne "
        f"vaut pas livrable : la section sera comptee comme non "
        f"faite. Ecris-le maintenant, ou supprime le fichier si "
        f"l'implementation vit ailleurs : un stub qui annonce "
        f"« rien ici » est pire que son absence."
    )
