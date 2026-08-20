"""Quelle pile technique ce projet a-t-il déjà choisie ? (HOS-134)

Mesuré sur la septième file : 26 sections lancées, six exécutées, et
**trois piles dans le même projet** — 14 fichiers `.ts`, 7 `.sql`, 6 `.py`.
Le même concept écrit deux fois, dans deux langages :

    db/migrations/20240920_create_workshops.ts
    db/migrations/20240920_create_employee_table.sql
    src/models/employee.ts        ← TypeScript
    src/models/position.py        ← Python

Chaque section choisissait sa pile indépendamment. Le §5 du cahier dit
pourtant « ne pas supposer une stack, déterminer l'architecture par
inspection » — et c'est exactement ce que personne ne faisait.

C'est aussi ce qui a bloqué §11 : un `PositionAuthorization` écrit en
Python, testé comme s'il suivait les conventions du modèle TypeScript
produit trois sections plus tôt.

## La mémoire des fichiers ne suffit pas

Le journal (HOS-123) transmet ce qui a été **produit**. Une section suivante
sait donc qu'`employee.ts` existe — et écrit quand même `position.py`.
Ce qui manquait n'est pas la liste des fichiers, c'est la **décision** qu'ils
incarnent.

## Détection mécanique, jamais un modèle

On compte les extensions de ce qui est sur le disque. Aucun appel modèle :
demander à un modèle quelle pile il « voit » rouvrirait la porte à
l'invention que ce module ferme.

Et quand il n'y a pas encore de code, on ne dit **rien** : imposer une pile
que personne n'a choisie serait exactement la supposition que le §5
interdit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

#: Extension -> nom de la pile. Volontairement court : on ne cherche pas à
#: reconnaître tous les écosystèmes, seulement à voir si le projet en a
#: déjà adopté un.
_PILES: dict[str, str] = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".kt": "Kotlin",
}

#: Ni du code applicatif, ni un choix de pile : du schéma, de la doc, de la
#: configuration. Les compter ferait de `.sql` une « pile » concurrente
#: alors qu'il accompagne n'importe laquelle.
_NEUTRES = frozenset({".sql", ".md", ".json", ".yaml", ".yml", ".toml",
                      ".txt", ".css", ".html", ".sh", ".env"})

_IGNORES = frozenset({".git", "__pycache__", ".venv", "venv", "node_modules",
                      ".pytest_cache", ".hermes", "dist", "build"})

#: En deçà, un seul fichier ne fait pas une architecture. Deux non plus :
#: une section peut légitimement écrire un script isolé dans un autre
#: langage sans que le projet ait « choisi ».
MINIMUM_FICHIERS = 3


def compter(workspace: Optional[str]) -> dict[str, int]:
    """Les fichiers de code par pile, tels qu'ils sont sur le disque."""
    if not workspace:
        return {}
    try:
        racine = Path(workspace).expanduser().resolve()
    except OSError:
        return {}
    if not racine.is_dir():
        return {}

    compte: dict[str, int] = {}
    for chemin in racine.rglob("*"):
        if not chemin.is_file():
            continue
        if any(part in _IGNORES for part in chemin.parts):
            continue
        suffixe = chemin.suffix.lower()
        if suffixe in _NEUTRES:
            continue
        pile = _PILES.get(suffixe)
        if pile:
            compte[pile] = compte.get(pile, 0) + 1
    return compte


def dominante(compte: dict[str, int]) -> Optional[str]:
    """La pile du projet, ou `None` s'il n'en a pas encore.

    `None` couvre deux situations qu'on ne cherche pas à distinguer — pas
    de code du tout, ou trop peu pour conclure — parce qu'elles appellent
    la même conduite : ne rien imposer.
    """
    if not compte:
        return None
    pile, n = max(compte.items(), key=lambda kv: kv[1])
    return pile if n >= MINIMUM_FICHIERS else None


def contrainte(workspace: Optional[str]) -> str:
    """Ce qu'on ajoute au brief d'une section, ou une chaîne vide.

    Formulé comme un **constat**, pas comme une préférence : la pile n'a
    pas été choisie par moi, elle est sur le disque. Une section qui aurait
    une vraie raison d'en changer doit pouvoir le dire — mais elle doit le
    dire, au lieu de le faire en silence.
    """
    compte = compter(workspace)
    pile = dominante(compte)
    if not pile:
        return ""

    detail = ", ".join(f"{n} fichier(s) {p}"
                       for p, n in sorted(compte.items(), key=lambda kv: -kv[1]))
    texte = (
        f"Ce projet est déjà écrit en **{pile}** — mesuré sur le disque : "
        f"{detail}. Écris cette étape en {pile}, avec les mêmes conventions "
        f"de nommage et d'arborescence que l'existant."
    )
    if len(compte) > 1:
        texte += (
            f"\n\nPlusieurs langages coexistent déjà, ce qui est un défaut de "
            f"ce projet et non un modèle à suivre. Aligne-toi sur "
            f"{pile} ; n'en ajoute pas un troisième."
        )
    texte += (
        "\n\nSi cette étape exige vraiment un autre langage, écris-le "
        "explicitement dans ton document de décisions avant de le faire."
    )
    return texte
