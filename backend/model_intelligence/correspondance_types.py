"""Le type d'une tâche, traduit dans la langue du routeur (HOS-150).

Le planificateur classe chaque tâche dans une `TaskCategory` — douze
valeurs, de `implementation` à `security`. Le routeur, lui, raisonne en
`TaskType` — dix valeurs, de `code_generation` à `general`. **Les deux
vocabulaires ne se recouvrent que sur trois mots.**

Mesuré le 2026-08-22 :

    analysis        reconnue
    documentation   reconnue
    optimization    reconnue
    design, implementation, testing, deployment, review,
    planning, integration, security, custom   -> jetees

Neuf catégories sur douze étaient donc **rejetées**, et le routeur retombait
sur une inférence par mots-clés du titre. L'ironie est dans le code
lui-même : le commentaire de `_task_type_hint` explique qu'il transmet « un
signal réel et plus précis que la ré-inférence par mots-clés » — et cette
valeur était jetée à l'arrivée, faute de vocabulaire commun.

Les deux catégories qui portent le code, `implementation` et `testing`,
étaient précisément du nombre.

## Les choix de traduction, et pourquoi

Chacun peut se discuter ; aucun n'est arbitraire.

* `testing` -> `code_generation` : écrire des tests est écrire du code. La
  compétence en jeu est la même, pas celle d'une relecture.
* `integration` -> `code_generation` : brancher deux modules s'écrit.
* `review` et `security` -> `code_review` : un audit de sécurité est une
  relecture, avec un angle. Les séparer demanderait un type que le routeur
  n'a pas.
* `design` et `planning` -> `reasoning` : on y décide avant d'écrire.
* `deployment` et `custom` -> `general` : faute de meilleur candidat, et
  c'est dit plutôt que déguisé en choix.

Une catégorie inconnue rend `None`, pas `general` : « je ne sais pas » doit
laisser l'inférence par mots-clés faire son travail, au lieu de la
court-circuiter par un type fourre-tout.
"""
from __future__ import annotations

from typing import Optional

#: Categorie du planificateur -> type du routeur. Ecrite en chaines plutot
#: qu'en enums pour que ce module ne depende ni de l'un ni de l'autre : il
#: est le pont, il ne doit pas tomber si l'un des deux bouge.
CORRESPONDANCE: dict[str, str] = {
    "analysis": "analysis",
    "design": "reasoning",
    "implementation": "code_generation",
    "testing": "code_generation",
    "documentation": "documentation",
    "deployment": "general",
    "review": "code_review",
    "planning": "reasoning",
    "integration": "code_generation",
    "optimization": "optimization",
    "security": "code_review",
    "custom": "general",
}


def type_du_routeur(categorie: Optional[str]) -> Optional[str]:
    """La `TaskType` correspondante, ou `None` si on ne sait pas.

    `None` est un choix : il laisse le routeur inférer depuis le titre,
    comme il le faisait déjà. Rendre `general` par défaut remplacerait une
    inconnue par une affirmation fausse — et le routeur traiterait alors un
    « écris le module d'authentification » comme une conversation.
    """
    if not categorie:
        return None
    return CORRESPONDANCE.get(str(categorie).strip().lower())


def est_du_code(categorie: Optional[str]) -> bool:
    """Cette tâche demande-t-elle d'écrire ou de relire du code ?

    Sert à l'attribution d'un modèle par catégorie : c'est la question que
    pose un opérateur qui veut confier le code à un modèle plus fort et
    laisser le reste à un modèle rapide.
    """
    return type_du_routeur(categorie) in {"code_generation", "code_review"}
