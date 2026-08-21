"""Un symbole référencé et jamais défini (HOS-135).

Trois lancements de la file, trois workspaces neufs, trois sections
différentes — et le **même** défaut à chaque fois :

    run 7  §11  AttributeError: 'PositionAuthorization' has no attribute 'id'
    run 8  §6   AttributeError: 'User' has no attribute '_current_time'
    run 9  §6   NameError: name 'Optional' is not defined

Ce n'est pas de la variance. Et aucun instrument existant ne le voit : la
porte de syntaxe (HOS-121) analyse chaque fichier et les trois **compilent
parfaitement** ; le détecteur de boucles d'import (HOS-124) cherche autre
chose ; le verdict des tests (HOS-119) l'attrape, mais à la **fin** de la
mission, une fois le temps dépensé.

Ce module répond à la même question que `pyflakes`, sans la dépendance et
sans rien exécuter — importer du code écrit par un modèle, c'est le lancer.

## Deux vérifications, pas une de plus

* **`self.X` jamais défini dans la classe** — les deux `AttributeError` ;
* **un nom utilisé, ni importé, ni défini, ni intégré** — le `NameError`.

## La règle qui gouverne tout ici

**Un faux échec coûte autant qu'un faux succès.** Cinq des huit défauts de
mesure de ce dépôt étaient des échecs imaginaires. Chaque fois qu'une
construction rend l'analyse incertaine — `import *`, `setattr`, une classe
qui hérite ou qui porte un décorateur — ce module **se tait** plutôt que de
risquer une accusation fausse.
"""
from __future__ import annotations

import ast
import builtins
from typing import Optional

_INTEGRES = frozenset(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__", "self", "cls",
}

#: Au-delà, on ne rend plus un diagnostic mais une liste de courses.
_MAX_CITES = 8

#: Ces appels peuvent poser n'importe quel attribut ou nom. Leur présence
#: rend l'analyse non concluante.
_OPAQUES = frozenset({"setattr", "globals", "vars", "exec", "eval"})


class _Portee(ast.NodeVisitor):
    """Ce que le module définit, et ce qu'il utilise."""

    def __init__(self) -> None:
        self.definis: set[str] = set()
        self.utilises: dict[str, int] = {}
        self.incertain = False

    def visit_Import(self, n: ast.Import) -> None:
        for a in n.names:
            self.definis.add(a.asname or a.name.split(".")[0])

    def visit_ImportFrom(self, n: ast.ImportFrom) -> None:
        for a in n.names:
            if a.name == "*":
                # On ne sait plus ce qui entre dans la portée. On se tait.
                self.incertain = True
            else:
                self.definis.add(a.asname or a.name)

    def visit_FunctionDef(self, n) -> None:
        self.definis.add(n.name)
        self.generic_visit(n)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, n: ast.ClassDef) -> None:
        self.definis.add(n.name)
        self.generic_visit(n)

    def visit_Name(self, n: ast.Name) -> None:
        if isinstance(n.ctx, (ast.Store, ast.Del)):
            self.definis.add(n.id)
        else:
            if n.id in _OPAQUES:
                self.incertain = True
            self.utilises.setdefault(n.id, n.lineno)

    def visit_arg(self, n: ast.arg) -> None:
        # `generic_visit` est indispensable : l'annotation est un enfant de
        # l'argument. Sans elle, `def f(x: Optional[int])` ne visitait
        # jamais `Optional` — exactement le defaut du run 9, que ce module
        # existe pour attraper et qu'il manquait.
        self.definis.add(n.arg)
        self.generic_visit(n)

    def visit_ExceptHandler(self, n: ast.ExceptHandler) -> None:
        if n.name:
            self.definis.add(n.name)
        self.generic_visit(n)

    def visit_Global(self, n: ast.Global) -> None:
        self.definis.update(n.names)

    visit_Nonlocal = visit_Global


def _noms_indefinis(arbre: ast.AST) -> list[tuple[str, int]]:
    p = _Portee()
    p.visit(arbre)
    if p.incertain:
        return []
    return sorted((nom, ligne) for nom, ligne in p.utilises.items()
                  if nom not in p.definis and nom not in _INTEGRES)


def _attributs_manquants(arbre: ast.AST) -> list[tuple[str, str, int]]:
    """`self.X` lu alors que la classe ne le pose jamais."""
    trouves: list[tuple[str, str, int]] = []
    for classe in [n for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)]:
        # Une classe qui hérite reçoit des attributs qu'on ne voit pas ici ;
        # un décorateur (dataclass…) peut en fabriquer. On se tait.
        heritee = [b for b in classe.bases
                   if not (isinstance(b, ast.Name) and b.id == "object")]
        if heritee or classe.decorator_list:
            continue

        poses: set[str] = set()
        lus: dict[str, int] = {}
        opaque = False
        # Les constantes de classe — `MAX_RETAINED = 100` — sont lues via
        # `self.MAX_RETAINED` et posees par une affectation simple dans le
        # corps de la classe. Les oublier produisait 20 faux positifs sur
        # les 574 fichiers de ce depot, tous de ce seul motif. On ne prend
        # que les enfants **directs** du corps : une variable locale d'une
        # methode ne definit pas un attribut.
        for direct in classe.body:
            if isinstance(direct, ast.Assign):
                for cible in direct.targets:
                    if isinstance(cible, ast.Name):
                        poses.add(cible.id)
            elif isinstance(direct, ast.AnnAssign) and                     isinstance(direct.target, ast.Name):
                poses.add(direct.target.id)
        for n in ast.walk(classe):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                poses.add(n.name)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                poses.add(n.target.id)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in _OPAQUES:
                opaque = True
            elif isinstance(n, ast.Attribute) and \
                    isinstance(n.value, ast.Name) and n.value.id == "self":
                if isinstance(n.ctx, ast.Store):
                    poses.add(n.attr)
                else:
                    lus.setdefault(n.attr, n.lineno)
        if opaque:
            continue
        for attr, ligne in sorted(lus.items()):
            if attr not in poses and not attr.startswith("__"):
                trouves.append((classe.name, attr, ligne))
    return trouves


def verdict(chemin: str, contenu: str) -> Optional[str]:
    """Le premier symbole manquant, ou `None`.

    `None` a deux sens — rien trouvé, ou analyse impossible — et
    l'appelant ne doit annoncer un succès dans aucun des deux.
    """
    if not chemin.lower().endswith(".py"):
        return None
    try:
        arbre = ast.parse(contenu, filename=chemin)
    except (SyntaxError, ValueError):
        # Relève de la porte de syntaxe. Diagnostiquer ici donnerait une
        # cause fausse.
        return None

    manquants = _attributs_manquants(arbre)
    if manquants:
        classe, attr, ligne = manquants[0]
        reste = f" (+{len(manquants) - 1} autre(s))" if len(manquants) > 1 else ""
        return (f"ligne {ligne} : `self.{attr}` est utilisé dans la classe "
                f"`{classe}` qui ne le définit nulle part{reste}")

    indefinis = _noms_indefinis(arbre)
    if indefinis:
        nom, ligne = indefinis[0]
        autres = ", ".join(n for n, _ in indefinis[1:_MAX_CITES])
        reste = f" (aussi : {autres})" if autres else ""
        return (f"ligne {ligne} : `{nom}` est utilisé sans être défini ni "
                f"importé{reste}")
    return None


def message(chemin: str, contenu: str) -> str:
    """Ce qu'on ajoute au retour d'outil, ou une chaîne vide."""
    erreur = verdict(chemin, contenu)
    if not erreur:
        return ""
    return (f"\nATTENTION : le fichier est sur le disque et il compile, mais "
            f"il référence un symbole qui n'existe pas — {erreur}. Corrige-le "
            f"maintenant : le code lèvera à l'exécution.")
