"""Marque tout ce répertoire comme `lent` (HOS-111).

Ces tests lancent le pipeline autonome de bout en bout — `start_goal()`
traverse la planification, la décomposition et de l'inférence réelle. Un
seul peut prendre plusieurs minutes, et le premier essai de les exécuter a
fini sur un délai de 120 s dépassé au milieu de `as_completed`.

Le marqueur est posé ici plutôt que fichier par fichier : un nouveau test
d'intégration l'hérite sans que personne ait à y penser, et il ne peut donc
pas rejoindre la boucle courte par oubli.

Les retirer de `testpaths` aurait été plus simple et aurait recréé
exactement l'angle mort que HOS-111 vient de fermer — 2 869 tests que
personne n'exécutait. Marqué et déselectionné se voit dans la
configuration ; absent des chemins ne se voit nulle part.
"""
from __future__ import annotations

from pathlib import Path

import pytest

#: Le repertoire de ce conftest. Le filtrage n'est pas cosmetique :
#: `pytest_collection_modifyitems` recoit **tous** les elements collectes,
#: pas seulement ceux situes sous le conftest qui declare le hook. Sans ce
#: filtre, le premier essai a marque `lent` les 4 112 tests du depot et la
#: boucle courte n'en executait plus aucun — un angle mort total, pose en
#: voulant en fermer un.
_ICI = Path(__file__).parent.resolve()


def pytest_collection_modifyitems(config, items):
    for item in items:
        chemin = Path(str(item.fspath)).resolve()
        if chemin.is_relative_to(_ICI):
            item.add_marker(pytest.mark.lent)
