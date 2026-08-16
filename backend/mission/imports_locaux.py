"""Les modules d'un livrable s'importent-ils en rond ? (HOS-124)

Mesuré sur deux missions consécutives : l'étape 2 a produit
`organization.py` et `workshop.py` qui s'importent mutuellement.

    ImportError: cannot import name 'Organization' from partially
    initialized module 'organization' (most likely due to a circular import)

Aucun instrument ne le voyait. La porte de syntaxe (HOS-121) analyse chaque
fichier isolément — les deux compilent parfaitement. Le verdict des tests
(HOS-119) l'aurait attrapé, mais il ne tourne qu'au niveau d'autonomie
`high` et seulement si le projet a des tests.

## Statique, et c'est un choix

On ne charge rien. Importer du code écrit par un modèle, c'est l'exécuter —
exactement ce que `verification_run` place derrière une décision
d'opérateur. Cette analyse-là est gratuite, ne s'arme sur aucun niveau, et
fonctionne sur un projet sans le moindre test.

Elle ne remplace pas le lancement des tests : une dépendance absente, une
erreur d'exécution, un import qui échoue pour une autre raison lui
échappent. Elle répond à une seule question, précisément.

## Fatal ou non — la distinction qui évite un faux échec

Toutes les boucles d'import ne cassent pas. `from N import nom` ne lève que
si `nom` n'est pas encore défini quand N est réimporté, c'est-à-dire si sa
définition vient **après** l'import qui referme la boucle. Une boucle où
les définitions précèdent les imports tourne sans erreur.

Signaler les deux comme des échecs fabriquerait des faux négatifs, et cinq
des huit défauts de mesure de ce dépôt étaient des échecs imaginaires. On
mesure donc la position réelle : la boucle est déclarée fatale quand on
peut le démontrer, signalée sinon.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes_os.mission.imports")

_IGNORES = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
    ".hermes", "build", "dist",
})

#: Au-delà, on analyse un dépôt et plus un livrable de mission ; le coût
#: cesse d'être négligeable et le verdict d'être lisible.
_MAX_FICHIERS = 300


class _Aretes(ast.NodeVisitor):
    """Les imports **au niveau module** seulement.

    Un import dans une fonction ne ferme jamais de boucle au chargement —
    c'est même la façon canonique de la casser. Le compter produirait un
    faux positif sur du code délibérément correct.
    """

    def __init__(self) -> None:
        self.imports: list[tuple[str, Optional[str], int]] = []
        self.definitions: dict[str, int] = {}
        self._profondeur = 0

    def _corps(self, noeud: ast.AST) -> None:
        self._profondeur += 1
        self.generic_visit(noeud)
        self._profondeur -= 1

    visit_FunctionDef = _corps
    visit_AsyncFunctionDef = _corps
    visit_ClassDef = _corps

    def visit_If(self, noeud: ast.If) -> None:
        # `if TYPE_CHECKING:` ne s'exécute pas à l'import : une boucle qui
        # n'existe que là est la correction, pas le défaut.
        cible = ast.unparse(noeud.test) if hasattr(ast, "unparse") else ""
        if "TYPE_CHECKING" in cible:
            return
        self.generic_visit(noeud)

    def visit_Import(self, noeud: ast.Import) -> None:
        if self._profondeur == 0:
            for alias in noeud.names:
                self.imports.append((alias.name.split(".")[0], None, noeud.lineno))

    def visit_ImportFrom(self, noeud: ast.ImportFrom) -> None:
        if self._profondeur == 0 and noeud.module and noeud.level == 0:
            base = noeud.module.split(".")[0]
            for alias in noeud.names:
                self.imports.append((base, alias.name, noeud.lineno))

    def visit_Assign(self, noeud: ast.Assign) -> None:
        if self._profondeur == 0:
            for cible in noeud.targets:
                if isinstance(cible, ast.Name):
                    self.definitions.setdefault(cible.id, noeud.lineno)
        self.generic_visit(noeud)


def _analyser(chemin: Path) -> Optional[_Aretes]:
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8", errors="replace"),
                          filename=str(chemin))
    except (SyntaxError, ValueError, OSError):
        # Un fichier qui ne compile pas relève de la porte de syntaxe, pas
        # d'ici. Le compter comme une boucle serait un diagnostic faux.
        return None
    visiteur = _Aretes()
    visiteur.visit(arbre)
    # Les définitions de haut niveau, avec leur ligne : c'est ce qui décide
    # si une boucle casse ou tourne.
    for noeud in arbre.body:
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            visiteur.definitions.setdefault(noeud.name, noeud.lineno)
    return visiteur


def _cycles(graphe: dict[str, set[str]]) -> list[list[str]]:
    """Les boucles élémentaires, chacune une fois."""
    trouves: list[list[str]] = []
    vus: set[tuple[str, ...]] = set()

    def marcher(depart: str, courant: str, chemin: list[str]) -> None:
        for suivant in sorted(graphe.get(courant, ())):
            if suivant == depart and len(chemin) >= 2:
                canonique = tuple(sorted(chemin))
                if canonique not in vus:
                    vus.add(canonique)
                    trouves.append(chemin + [depart])
            elif suivant not in chemin and len(chemin) < 8:
                marcher(depart, suivant, chemin + [suivant])

    for module in sorted(graphe):
        marcher(module, module, [module])
    return trouves


def verdict(workspace: Optional[str]) -> Optional[dict]:
    """Les boucles d'import entre modules locaux, ou `None`.

    `None` = rien à analyser (pas de workspace, aucun `.py` lisible). Ce
    n'est pas « aucune boucle » : les deux se distinguent, comme partout
    ailleurs ici.
    """
    if not workspace:
        return None
    try:
        racine = Path(workspace).expanduser().resolve()
    except OSError:
        return None
    if not racine.is_dir():
        return None

    fichiers: dict[str, Path] = {}
    analyses: dict[str, _Aretes] = {}
    # Trié par profondeur : à nom de module égal, le plus proche de la
    # racine gagne. Sans ça le dernier trouvé l'emportait, et un doublon
    # enfoui — exactement ce que produit l'arbre fantôme de HOS-123b —
    # masquait le vrai module. Mesuré : le `organization.py` fantôme
    # faisait 140 octets sans un seul import, et sa présence effaçait la
    # boucle que ce module est censé détecter.
    for chemin in sorted(racine.rglob("*.py"), key=lambda p: (len(p.parts), str(p))):
        if any(part in _IGNORES for part in chemin.parts):
            continue
        if len(fichiers) >= _MAX_FICHIERS:
            break
        fichiers.setdefault(chemin.stem, chemin)
    if not fichiers:
        return None

    for nom, chemin in fichiers.items():
        analyse = _analyser(chemin)
        if analyse is not None:
            analyses[nom] = analyse
    if not analyses:
        return None

    graphe = {
        nom: {cible for cible, _, _ in analyse.imports
              if cible in analyses and cible != nom}
        for nom, analyse in analyses.items()
    }
    boucles = _cycles(graphe)
    if not boucles:
        return {"modules": len(analyses), "cycles": [], "fatals": []}

    fatals: list[str] = []
    decrits: list[str] = []
    for boucle in boucles:
        texte = " -> ".join(boucle)
        decrits.append(texte)
        if _est_fatale(boucle, analyses):
            fatals.append(texte)
    return {"modules": len(analyses), "cycles": decrits, "fatals": fatals}


def _est_fatale(boucle: list[str], analyses: dict[str, _Aretes]) -> bool:
    """Peut-on démontrer que cette boucle lève à l'import ?

    Le critère : quelque part dans la boucle, un module fait
    `from N import nom` alors que `nom` est défini dans N **après** l'import
    par lequel N referme la boucle. À ce moment-là N est partiellement
    initialisé et le nom n'existe pas encore — c'est exactement l'erreur
    mesurée sur `organization` / `workshop`.
    """
    for i in range(len(boucle) - 1):
        source, cible = boucle[i], boucle[i + 1]
        analyse_cible = analyses.get(cible)
        analyse_source = analyses.get(source)
        if analyse_cible is None or analyse_source is None:
            continue
        for module_importe, nom, _ligne in analyse_source.imports:
            if module_importe != cible or nom is None:
                continue
            ligne_definition = analyse_cible.definitions.get(nom)
            if ligne_definition is None:
                # `from N import nom` où N ne définit pas `nom` au niveau
                # module : l'import échouera de toute façon.
                return True
            lignes_import = [l for m, _, l in analyse_cible.imports
                             if m in boucle]
            if lignes_import and ligne_definition > min(lignes_import):
                return True
    return False


def contredit(verdict_imports: Optional[dict]) -> bool:
    """Seules les boucles démontrées fatales contredisent un succès.

    Une boucle non démontrée fatale reste signalée : elle casse au premier
    changement d'ordre d'import. Mais la traiter comme un échec
    fabriquerait des faux négatifs sur du code qui tourne.
    """
    return bool(verdict_imports) and bool(verdict_imports.get("fatals"))
