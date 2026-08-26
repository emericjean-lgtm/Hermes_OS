"""Ce projet a-t-il déjà un point d'entrée, et lequel ? (HOS-169)

Mesuré sur le projet livré par la campagne Skill360 — 20 sections abouties,
124 fichiers, 74 tests verts — et pourtant **huit applications distinctes** :

    api/atelier.py                      app = FastAPI(title="Atelier API")
    employees_api.py                    app = FastAPI(title="Employee API")
    backend/api/employee_assignment.py  app = FastAPI()
    backend/api/position_skill.py       app = FastAPI()
    backend/api/position_training.py    app = FastAPI()
    backend/api/static_routes.py        app = FastAPI()
    backend/api/kpi.py                  router = FastAPI(tags=["kpi"])
    backend/api/risk.py                 router = FastAPI(tags=["risk"])

Les deux dernières vont jusqu'à instancier une application en l'appelant
`router` — le nom dit l'intention, le code fait l'inverse.

Le seul `include_router` du projet est celui où `static_routes` inclut son
propre routeur. **Rien n'assemble ces huit applications.** Le projet ne
démarre pas comme un service ; il démarre comme six services qui s'ignorent.

## Le troisième maillon d'une même chaîne

`pile.py` transmet la décision de **langage** que les fichiers incarnent,
parce que la liste des fichiers produits ne la portait pas — une section
savait qu'`employee.ts` existait et écrivait quand même `position.py`.

`arborescence.py` transmet la décision d'**emplacement**, pour la même
raison — une section annonçait `backend/models/x.py` alors que `models/x.py`
existait déjà.

Il manquait la décision d'**assemblage**. Chaque section fait exactement ce
qu'on lui demande — « réalise une seule étape » — et rien ne lui dit qu'un
service existe déjà, ni où brancher ce qu'elle écrit. Le modèle n'a pas
échoué : personne ne lui a posé la question.

## Détection mécanique, jamais un modèle

On compte les points d'entrée sur le disque. Aucun appel modèle : demander
à un modèle où il « croit » que vit l'application rouvrirait la porte à
l'invention que ce module ferme.

Et sur un projet qui n'en a aucun, on ne dit **rien** : imposer une
architecture que personne n'a choisie serait la supposition que le §5 d'un
cahier interdit — la même retenue que ses deux prédécesseurs.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".hermes",
           ".pytest_cache", "build", "dist", "migrations"}

#: Les cadres dont une instanciation déclare une application montable.
#:
#: Cherchés par leur **nom d'appel** dans l'AST, jamais par recherche de
#: chaîne : ce module contient lui-même « FastAPI( » dans son propre texte,
#: et se signalait donc comme point d'entrée. Le test qui inspecte le dépôt
#: l'a attrapé au premier essai.
#:
#: Limite assumée : une application construite par une fabrique
#: (`def creer_app(): return FastAPI()`) n'est pas vue. C'est le cas de
#: `backend/main.py` dans ce dépôt. Élargir la détection au corps des
#: fonctions signalerait toutes les fabriques de test, ce qui coûterait
#: plus de faux positifs que le cas ne le vaut.
CADRES_PYTHON = {"FastAPI", "Flask", "Starlette", "Sanic", "Quart"}

CADRES_JS: dict[str, str] = {"express(": "Express", "Fastify(": "Fastify"}

#: Un fichier de test qui monte son propre client n'est pas un point
#: d'entrée du projet — c'est un banc d'essai.
def _est_un_test(chemin: Path) -> bool:
    nom = chemin.name
    return (nom.startswith("test_") or nom.endswith("_test.py")
            or "tests" in chemin.parts)


def _cadre_instancie(source: str) -> Optional[str]:
    """Le cadre reellement **instancie** au niveau module, ou None.

    Par l'AST et non par recherche de chaine : ce module contient lui-meme
    la chaine `FastAPI(` dans son dictionnaire de motifs, et se signalait
    donc comme point d'entree. Le test qui inspecte le depot l'a attrape du
    premier coup — c'est ce pour quoi il existe.
    """
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        return None
    for noeud in arbre.body:
        if not isinstance(noeud, (ast.Assign, ast.AnnAssign)):
            continue
        valeur = noeud.value
        if not isinstance(valeur, ast.Call):
            continue
        nom = (getattr(valeur.func, "id", None)
               or getattr(valeur.func, "attr", None) or "")
        if nom in CADRES_PYTHON:
            return nom
    return None


def points_d_entree(workspace: Optional[str]) -> list[tuple[str, str]]:
    """Les `(chemin, cadre)` des applications declarees dans ce projet."""
    trouves: list[tuple[str, str]] = []
    if not workspace:
        return trouves
    base = Path(workspace)
    if not base.is_dir():
        return trouves

    for fichier in sorted(base.rglob("*.py")):
        if any(p in IGNORES for p in fichier.parts) or _est_un_test(fichier):
            continue
        try:
            source = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cadre = _cadre_instancie(source)
        if cadre:
            trouves.append((fichier.relative_to(base).as_posix(), cadre))

    # Hors Python, faute d'AST : une recherche de chaine, bornee aux cadres
    # dont le nom ne se confond avec rien d'autre.
    for motif in ("*.js", "*.ts"):
        for fichier in sorted(base.rglob(motif)):
            if any(p in IGNORES for p in fichier.parts) or _est_un_test(fichier):
                continue
            try:
                source = fichier.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for aiguille, cadre in CADRES_JS.items():
                if aiguille in source:
                    trouves.append(
                        (fichier.relative_to(base).as_posix(), cadre))
                    break
    return trouves


def monte_un_routeur(workspace: Optional[str]) -> bool:
    """Le projet assemble-t-il déjà quelque chose ?

    Un `include_router` ou un `app.use` qui pointe **ailleurs** que sur le
    fichier lui-même est le signe qu'un assemblage existe. On ne cherche pas
    à le suivre : sa seule présence change ce qu'on a à dire.
    """
    if not workspace:
        return False
    base = Path(workspace)
    if not base.is_dir():
        return False
    motif = re.compile(r"include_router\s*\(\s*(\w+)\.", re.M)
    for fichier in base.rglob("*.py"):
        if any(p in IGNORES for p in fichier.parts) or _est_un_test(fichier):
            continue
        try:
            if motif.search(fichier.read_text(encoding="utf-8",
                                              errors="replace")):
                return True
        except OSError:
            continue
    return False


def contrainte(workspace: Optional[str]) -> str:
    """Ce qu'on dit à l'agent, ou "" quand il n'y a rien à imposer."""
    entrees = points_d_entree(workspace)
    if not entrees:
        # Rien n'a encore été décidé : laisser la section choisir.
        return ""

    lignes = "\n    ".join(f"{c:<44} ({cadre})" for c, cadre in entrees[:10])

    if len(entrees) == 1:
        chemin, cadre = entrees[0]
        return (
            f"\n\nCE PROJET A DÉJÀ UNE APPLICATION — relevée sur le disque :"
            f"\n\n    {chemin}  ({cadre})\n\n"
            f"N'en crée pas une seconde. Écris tes routes dans un routeur "
            f"(`APIRouter`, `Blueprint`, `Router` selon le cadre) et "
            f"**monte-le dans cette application-là**. Une application par "
            f"section donnerait un projet qui ne démarre pas."
        )

    return (
        f"\n\nCE PROJET A {len(entrees)} APPLICATIONS DISTINCTES — relevées "
        f"sur le disque :\n\n    {lignes}\n\n"
        f"C'est un défaut : un projet n'a qu'un point d'entrée. Ne fais "
        f"surtout pas la {len(entrees) + 1}ᵉ. Choisis celle qui sert de "
        f"racine, transforme les autres en routeurs, et monte-les dedans. "
        f"Si ta section ne porte pas sur l'architecture, écris au moins tes "
        f"propres routes dans un routeur montable plutôt que dans une "
        f"application neuve."
    )
