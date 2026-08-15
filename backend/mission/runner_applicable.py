"""Quel runner de tests s'applique à ce workspace, s'il y en a un (HOS-119).

Mesuré : un cahier des charges de trois livrables a produit un module
correct, ses tests, sa documentation — et **les tests ne passaient pas**.
Le modèle avait nommé le fichier `calculatrice.py` et importé `calculator`.
La mission a rapporté 6/6 réussi.

`MissionVerification` répond à « le workspace a-t-il changé ? ». La réponse
était oui, six fois. Elle ne répond pas à « ce qui a été produit tient-il
debout ? ». Ce module fournit l'entrée manquante.

## Pourquoi une détection par le contenu du dossier

`verification.list_runners()` rend la liste blanche *globale*. Lancer
`pytest` sur un projet JavaScript échouerait pour une raison qui n'a rien
à voir avec le travail fait — et marquerait en échec une mission
parfaitement bonne. Un faux échec est aussi nuisible qu'un faux succès :
c'est la leçon la plus chère de ce dépôt, cinq défauts de mesure sur huit
produisaient des échecs imaginaires.

On ne propose donc un runner que si le dossier porte la marque de
l'écosystème correspondant, et on rend `None` sans état d'âme sinon.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

#: (nom du runner, marqueurs qui prouvent que l'écosystème est là).
#: L'ordre compte : un dépôt qui porte les deux est d'abord jugé sur ses
#: tests Python, parce que c'est le cas de ce dépôt-ci et qu'un choix
#: arbitraire vaut mieux qu'un choix implicite.
_MARQUEURS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pytest", ("pytest.ini", "pyproject.toml", "setup.cfg", "conftest.py")),
    ("npm_test", ("package.json",)),
)

#: Un fichier de test suffit à déclarer l'écosystème Python, même sans
#: fichier de configuration : c'est le cas d'un dossier fraîchement produit
#: par une mission, qui écrit `test_x.py` avant d'écrire `pytest.ini`.
_MOTIFS_TESTS_PYTHON = ("test_*.py", "*_test.py", "tests/test_*.py")


def runner_pour(root: str) -> Optional[str]:
    """Le runner applicable à ce dossier, ou None.

    None n'est pas un échec : c'est « on ne peut rien conclure », et
    l'appelant doit le rapporter comme tel plutôt que de le lire comme un
    succès.
    """
    try:
        dossier = Path(root).expanduser().resolve()
    except OSError:
        return None
    if not dossier.is_dir():
        return None

    for nom, marqueurs in _MARQUEURS:
        if any((dossier / m).exists() for m in marqueurs):
            return nom

    for motif in _MOTIFS_TESTS_PYTHON:
        if next(dossier.glob(motif), None) is not None:
            return "pytest"
    return None
