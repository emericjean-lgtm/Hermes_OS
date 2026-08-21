"""Les scripts livres doivent compiler (HOS-136).

`scripts/derouler_cahier.py` a ete **commite casse** : une chaine non
terminee, introduite par une edition ou `\n` avait ete collapse en vrai
saut de ligne. La suite de tests est passee au vert — 4 185 tests — parce
qu'aucun test n'importe les scripts.

C'est la meme famille de defaut que `backend/tools/syntaxe.py` attrape pour
le code ecrit par un modele. Il n'y avait aucune raison que le code ecrit
ici en soit dispense.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SCRIPTS = sorted(p for p in Path("scripts").rglob("*.py")
                  if "__pycache__" not in p.parts)


@pytest.mark.parametrize("chemin", _SCRIPTS, ids=lambda p: p.name)
def test_le_script_compile(chemin: Path):
    source = chemin.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(source, filename=str(chemin))
    except SyntaxError as erreur:
        pytest.fail(f"{chemin} ligne {erreur.lineno} : {erreur.msg}")


def test_il_y_a_bien_des_scripts_a_verifier():
    """Sans ca, un `scripts/` vide rendrait ce module trivialement vert."""
    assert len(_SCRIPTS) >= 3
