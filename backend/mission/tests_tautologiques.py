"""Des tests verts qui ne peuvent pas echouer (HOS-153).

Une suite verte est la preuve que le harnais exige avant de declarer une
section verifiee. Elle ne vaut que si les tests peuvent rougir.

Ce module a une histoire courte et embarrassante : le premier defaut de ce
genre a ete ecrit **par l'assistant lui-meme**, pas par un modele local. Les
tests du garde-fou de workspace passaient `args=...` a un hook qui lisait
`tool_input`. Six tests verts, une protection inerte, et personne pour le
voir — parce qu'un test vert ne se relit pas.

## Pourquoi ce garde est volontairement etroit

Il ne signale que ce qu'il peut **demontrer** constant. Un test sans
assertion n'est pas signale : `def test_import(): import monmodule` est un
test legitime, qui echoue si l'import leve. Un garde qui le refuserait
produirait des faux echecs — et ce projet a deja mesure que cinq de ses huit
defauts d'instrumentation produisaient de faux echecs, pas de faux succes.

Sont donc signalees les seules assertions dont la valeur se calcule sans
executer le programme :

    assert True                 une constante vraie
    assert 1 == 1               deux constantes, comparaison decidable
    assert resultat == resultat un terme compare a lui-meme
    assert not False            la negation d'une constante fausse

Rien d'autre. C'est peu, et c'est le prix pour que ce garde n'ait jamais
tort.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

#: Les comparaisons vraies par construction quand les deux termes sont le
#: meme. `!=` et `<` ne sont pas du lot : `x != x` est faux, pas tautologique,
#: et signaler une assertion **toujours fausse** demande un autre message.
_REFLEXIVES = (ast.Eq, ast.Is, ast.LtE, ast.GtE)

_IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".hermes"}


def _constante_vraie(noeud: ast.expr) -> bool:
    """Ce terme est-il une constante litterale dont la verite est acquise ?"""
    if isinstance(noeud, ast.Constant):
        return bool(noeud.value)
    # `[]`, `{}`, `()` litteraux non vides sont vrais sans rien evaluer —
    # mais seulement si tous leurs elements sont eux-memes litteraux, sans
    # quoi on prejugerait d'un appel.
    if isinstance(noeud, (ast.List, ast.Tuple, ast.Set)):
        return bool(noeud.elts) and all(
            isinstance(e, ast.Constant) for e in noeud.elts)
    return False


def _memes_termes(gauche: ast.expr, droite: ast.expr) -> bool:
    """Les deux cotes sont-ils syntaxiquement le meme terme ?

    Compare la forme, pas la valeur : `a.b[0]` et `a.b[0]` sont le meme
    terme. Les appels sont exclus — `f() == f()` peut echouer, c'est meme
    souvent tout l'interet du test.
    """
    if any(isinstance(n, ast.Call)
           for cote in (gauche, droite)
           for n in ast.walk(cote)):
        return False
    return ast.dump(gauche) == ast.dump(droite)


def _pourquoi_tautologique(test: ast.expr) -> str:
    """La raison, en une phrase, ou "" si l'assertion peut echouer."""
    if _constante_vraie(test):
        return "la condition est une constante vraie"

    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        cible = test.operand
        if isinstance(cible, ast.Constant) and not cible.value:
            return "la condition nie une constante fausse"

    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        gauche, op, droite = test.left, test.ops[0], test.comparators[0]
        if isinstance(op, _REFLEXIVES) and _memes_termes(gauche, droite):
            return "les deux cotes de la comparaison sont le meme terme"
        if (isinstance(gauche, ast.Constant)
                and isinstance(droite, ast.Constant)):
            try:
                decide = bool(ast.literal_eval(ast.Expression(body=test)))
            except (ValueError, TypeError, SyntaxError):
                return ""
            if decide:
                return "deux constantes comparees : l'issue est ecrite"
    return ""


def fautes_du_source(source: str) -> list[tuple[int, str, str]]:
    """Les `(ligne, fonction, raison)` des assertions qui ne peuvent echouer.

    Ne regarde que les fonctions dont le nom commence par `test_` : une
    assertion constante dans du code de production est souvent une garde
    d'invariant deliberee, alors que dans un test elle n'a aucun sens.
    """
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        # Un fichier qui ne compile pas est deja un echec visible ; ce n'est
        # pas a ce garde de le rapporter.
        return []

    fautes: list[tuple[int, str, str]] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not noeud.name.startswith("test_"):
            continue
        for interne in ast.walk(noeud):
            if not isinstance(interne, ast.Assert):
                continue
            raison = _pourquoi_tautologique(interne.test)
            if raison:
                fautes.append((interne.lineno, noeud.name, raison))
    return fautes


def verdict(racine: str) -> Optional[dict]:
    """La premiere assertion inconditionnellement vraie du projet, ou None."""
    base = Path(racine)
    if not base.is_dir():
        return None
    for fichier in sorted(base.rglob("*.py")):
        if any(p in _IGNORES for p in fichier.parts):
            continue
        if not (fichier.name.startswith("test_")
                or fichier.name.endswith("_test.py")):
            continue
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ligne, fonction, raison in fautes_du_source(source):
            return {
                "fichier": str(fichier.relative_to(base)),
                "ligne": ligne,
                "fonction": fonction,
                "raison": raison,
            }
    return None


def message(racine: str) -> str:
    """Ce qu'on dit a l'agent, ou "" s'il n'y a rien a dire."""
    faute = verdict(racine)
    if faute is None:
        return ""
    return (
        f"\n\nTEST QUI NE PEUT PAS ECHOUER — {faute['fichier']}:"
        f"{faute['ligne']}, dans {faute['fonction']}()\n"
        f"L'assertion passe quoi qu'il arrive : {faute['raison']}.\n"
        f"Une suite verte est la preuve qu'on te demande ; un test qui ne "
        f"peut pas rougir n'en est pas une. Fais porter l'assertion sur le "
        f"resultat reel de la fonction testee, et verifie qu'elle echoue si "
        f"tu casses cette fonction."
    )


def message_du_fichier(chemin: str, source: str) -> str:
    """Le meme avertissement, mais **au moment de l'ecriture**.

    Dit a la verification, il coute deux passes : la section est declaree
    faite, la suite verte sert de preuve, et le defaut ne se decouvre qu'au
    dépouillement. Dit ici, il coute un tour.
    """
    nom = Path(chemin).name
    if not (nom.startswith("test_") or nom.endswith("_test.py")):
        return ""
    fautes = fautes_du_source(source)
    if not fautes:
        return ""
    ligne, fonction, raison = fautes[0]
    return (
        f"\n\nATTENTION — {nom}:{ligne}, dans {fonction}() : cette assertion "
        f"passe quoi qu'il arrive ({raison}). Un test qui ne peut pas rougir "
        f"ne prouve rien. Fais-la porter sur le resultat reel, et verifie "
        f"qu'elle echoue si tu casses la fonction testee."
    )
