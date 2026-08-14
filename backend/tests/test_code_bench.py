"""Le juge de compétence en codage (HOS-106).

Un vérificateur faux produit un verdict confiant et faux — trois fois
aujourd'hui, un défaut d'instrument a failli écarter un modèle capable.
Ici l'enjeu est double : accepter du code correct entouré de prose, et
refuser du code qui ne fait pas ce qu'on demande.
"""
from __future__ import annotations

import pytest

from backend.model_intelligence.code_bench import (
    TASKS, extract_code, run_code_task,
)

SIMPLE = next(t for t in TASKS if t.level == "simple")
BON = '''
def compter_mots(texte):
    out = {}
    for mot in texte.lower().split():
        out[mot] = out.get(mot, 0) + 1
    return out
'''


# ── extraction ───────────────────────────────────────────────────────────

def test_le_code_encadre_est_extrait():
    assert "def compter_mots" in extract_code(f"Voici :\n```python\n{BON}\n```\nVoilà.")


def test_le_code_nu_passe_tel_quel():
    assert "def compter_mots" in extract_code(BON)


def test_le_plus_long_bloc_gagne():
    """Les modèles esquissent souvent un extrait avant la vraie réponse."""
    raw = f"D'abord :\n```python\nx = 1\n```\nPuis :\n```python\n{BON}\n```"

    assert "def compter_mots" in extract_code(raw)


# ── exécution ────────────────────────────────────────────────────────────

def test_du_code_correct_passe():
    result = run_code_task(SIMPLE, BON)

    assert result.passed, result.detail


def test_du_code_correct_entoure_de_prose_passe():
    """Refuser ça mesurerait la mise en forme, pas la compétence."""
    assert run_code_task(SIMPLE, f"Bien sûr !\n```python\n{BON}\n```\nJ'espère.").passed


def test_du_code_qui_ignore_la_casse_echoue():
    """L'énoncé demande d'ignorer la casse. Un code qui ne le fait pas doit
    échouer — c'est la différence entre exécuter et relire."""
    sans_casse = BON.replace(".lower()", "")

    result = run_code_task(SIMPLE, sans_casse)

    assert not result.passed


def test_une_reponse_vide_echoue():
    assert not run_code_task(SIMPLE, "").passed


def test_du_code_invalide_echoue_sans_faire_tomber_le_banc():
    result = run_code_task(SIMPLE, "def compter_mots(texte)\n    return {}")

    assert not result.passed
    assert result.detail


def test_une_boucle_infinie_expire_au_lieu_de_bloquer():
    """Un modèle qui écrit une boucle sans fin doit coûter un essai, pas la
    campagne. C'est la raison d'être du sous-processus."""
    result = run_code_task(SIMPLE, "def compter_mots(texte):\n    while True:\n        pass")

    assert not result.passed
    assert "expiré" in result.detail


def test_le_code_ne_sexecute_pas_dans_ce_processus():
    """Preuve par l'absurde : un `sys.exit` dans la réponse tuerait le banc
    s'il était exécuté ici."""
    result = run_code_task(SIMPLE, "import sys\nsys.exit(3)\ndef compter_mots(t): return {}")

    assert not result.passed  # et surtout : ce test se termine


# ── les épreuves elles-mêmes ─────────────────────────────────────────────

@pytest.mark.parametrize("level", ["simple", "moyen", "complexe"])
def test_chaque_niveau_existe(level):
    assert any(t.level == level for t in TASKS)


def test_les_assertions_du_niveau_moyen_depassent_l_enonce():
    """Le niveau moyen doit tester ce que l'énoncé ne dit pas — sinon il ne
    distingue pas un modèle qui anticipe d'un modèle qui recopie."""
    moyen = next(t for t in TASKS if t.level == "moyen")

    assert "fusionner([])" in moyen.checks
    assert "(1, 2), (2, 3)" in moyen.checks


def test_une_solution_de_reference_passe_le_niveau_moyen():
    """Si aucune solution correcte ne passait, l'épreuve serait fausse."""
    moyen = next(t for t in TASKS if t.level == "moyen")
    reference = '''
def fusionner(intervalles):
    if not intervalles:
        return []
    out = []
    for debut, fin in sorted(intervalles):
        if out and debut <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], fin))
        else:
            out.append((debut, fin))
    return out
'''

    assert run_code_task(moyen, reference).passed


def test_une_solution_de_reference_passe_le_niveau_complexe():
    complexe = next(t for t in TASKS if t.level == "complexe")
    reference = '''
class Compte:
    def __init__(self):
        self._ops = []
    def depot(self, montant):
        self._ops.append(montant)
    def retrait(self, montant):
        if montant > self.solde():
            raise ValueError("solde insuffisant")
        self._ops.append(-montant)
    def solde(self):
        return sum(self._ops)
    def annuler(self):
        if self._ops:
            self._ops.pop()
'''

    assert run_code_task(complexe, reference).passed
