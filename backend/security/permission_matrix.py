"""Typed view over config/security.yaml.

Nothing outside this module should read the raw security.yaml dict —
AegisEngine and anything else that needs a policy goes through
PermissionMatrix.get_category().
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CategoryPolicy:
    name: str
    mutating: bool
    path_based: bool
    mandatory_validation: bool
    # Minimum autonomy level ("low"/"medium"/"high") at which this
    # category may be auto-allowed. Irrelevant when mandatory_validation
    # is True (always requires a human) or mutating is False (always
    # allowed, subject to the path whitelist).
    min_autonomy_for_auto_allow: str | None = None


class PermissionMatrix:
    def __init__(self, config: dict[str, Any]) -> None:
        # La dérogation d'exécution l'emporte sur le fichier, quand il y en
        # a une (HOS-115). `AegisEngine` relit `autonomy_level` à chaque
        # évaluation, donc changer cet attribut prend effet immédiatement —
        # c'est ce qui permet un curseur dans l'interface plutôt qu'une
        # édition de fichier suivie d'un redémarrage.
        from backend.security.autonomy import lire_derogation

        self.autonomy_level: str = lire_derogation() or config.get("autonomy_level", "low")
        self._categories: dict[str, CategoryPolicy] = {
            name: CategoryPolicy(
                name=name,
                mutating=spec.get("mutating", True),
                path_based=spec.get("path_based", False),
                mandatory_validation=spec.get("mandatory_validation", False),
                min_autonomy_for_auto_allow=spec.get("min_autonomy_for_auto_allow"),
            )
            for name, spec in config.get("action_categories", {}).items()
        }

    def get_category(self, action_type: str) -> CategoryPolicy | None:
        return self._categories.get(action_type)

    def known_categories(self) -> list[str]:
        return sorted(self._categories)
