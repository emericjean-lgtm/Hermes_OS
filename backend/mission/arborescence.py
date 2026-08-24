"""Où ce projet range-t-il déjà ses fichiers ? (HOS-159)

Mesuré sur la campagne Skill360 du 2026-08-24, **trois sections d'affilée**
déclarées `signalée (contredite)` pour la même raison — un livrable annoncé
à un chemin, écrit à un autre :

    §11  annonce tests/test_position_models.py    absent
    §12  annonce backend/models/position_skill.py absent
    §13  annonce docs/required_level.md           absent

Ce n'était pas un défaut de nommage. Le workspace portait **trois
arborescences parallèles** :

    8  models/          2  backend/api/     1  api/
    7  tests/           1  backend/         1  migrations/
    2  skills/          + six fichiers a la racine

§12 a annoncé `backend/models/position_skill.py` alors que §11 avait créé
`models/position_skill.py` deux minutes plus tôt. §13 a écrit
`tests/docs/required_level.md` — un dossier `docs` **dans** `tests` — et
inventé au passage `sitecustomize.py` et un dossier `skills/`.

Chaque section reconstruisait une structure. Le résultat final aurait été
inutilisable quelle que soit la qualité de chaque fichier pris isolément.

## Le même défaut que la pile, un cran plus haut

`backend/mission/pile.py` transmet la **décision** de langage que les
fichiers incarnent, parce que la mémoire des fichiers produits ne suffisait
pas — une section savait qu'`employee.ts` existait et écrivait quand même
`position.py`. Ici c'est la décision d'**emplacement**, et elle manquait
pour exactement la même raison.

## Détection mécanique, jamais un modèle

On liste les dossiers qui contiennent réellement du code. Aucun appel
modèle : demander à un modèle où il « croit » que vivent les fichiers
rouvrirait la porte à l'invention que ce module ferme.

Et quand le projet est vide, on ne dit **rien**. Imposer une arborescence
que personne n'a choisie serait la supposition que le §5 du cahier interdit
— la même retenue que `pile.contrainte`.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

#: Ce qu'on ne compte jamais comme un choix d'architecture.
IGNORES = {"__pycache__", ".venv", "venv", "node_modules", ".git", ".hermes",
           ".pytest_cache", "build", "dist", ".mypy_cache", ".idea"}

#: Les extensions qui portent du code. Un dossier plein de `.md` n'est pas
#: une décision d'architecture, c'est de la documentation.
CODE = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql", ".go", ".rs", ".java"}

#: En dessous, il n'y a pas encore d'arborescence à respecter. Deux fichiers
#: ne font pas une convention ; ils font un début qu'une section a le droit
#: de réorganiser.
MINIMUM_FICHIERS = 3

#: Au-delà, la liste cesse d'être lisible et se fait ignorer — le même
#: raisonnement que le rappel des compétences, qui nomme les domaines et non
#: les quatre-vingts fiches.
PLAFOND_DOSSIERS = 12


def dossiers_de_code(workspace: Optional[str]) -> Counter:
    """Les dossiers qui contiennent du code, et combien de fichiers chacun.

    La racine compte comme un dossier à part entière, sous le nom `.` :
    c'est un emplacement légitime, et le taire ferait croire qu'il faut
    créer un dossier pour tout.
    """
    compte: Counter = Counter()
    if not workspace:
        return compte
    base = Path(workspace)
    if not base.is_dir():
        return compte
    for fichier in base.rglob("*"):
        if not fichier.is_file() or fichier.suffix.lower() not in CODE:
            continue
        if any(p in IGNORES for p in fichier.parts):
            continue
        try:
            relatif = fichier.relative_to(base)
        except ValueError:
            continue
        parent = relatif.parent.as_posix()
        compte[parent if parent != "." else "."] += 1
    return compte


def contrainte(workspace: Optional[str]) -> str:
    """Ce qu'on dit à l'agent, ou "" quand il n'y a rien à imposer."""
    compte = dossiers_de_code(workspace)
    total = sum(compte.values())
    if total < MINIMUM_FICHIERS:
        # Rien n'a encore été décidé : laisser la section choisir.
        return ""

    lignes = [
        f"{('la racine' if d == '.' else d + '/'):<28} {n} fichier(s)"
        for d, n in compte.most_common(PLAFOND_DOSSIERS)
    ]
    return (
        "\n\nOÙ CE PROJET RANGE DÉJÀ SES FICHIERS — relevé sur le disque, "
        "pas supposé :\n\n    "
        + "\n    ".join(lignes)
        + "\n\nÉcris tes livrables **dans ces dossiers**. N'en crée un "
        "nouveau que si aucun ne convient, et dis-le alors explicitement.\n"
        "Vérifie qu'un fichier n'existe pas déjà sous un autre chemin avant "
        "d'en créer un : trois sections de ce cahier ont annoncé "
        "`backend/models/x.py` alors que `models/x.py` existait déjà.\n"
        "Le chemin que tu annonces comme livrable doit être **exactement** "
        "celui où tu écris, relatif à la racine du projet."
    )
