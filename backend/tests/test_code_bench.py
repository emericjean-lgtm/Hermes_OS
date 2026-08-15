"""Le juge de compétence en codage (HOS-106).

Un vérificateur faux produit un verdict confiant et faux — trois fois
aujourd'hui, un défaut d'instrument a failli écarter un modèle capable.
Ici l'enjeu est double : accepter du code correct entouré de prose, et
refuser du code qui ne fait pas ce qu'on demande.
"""
from __future__ import annotations

import pytest

from backend.model_intelligence import code_bench
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


def test_le_plus_long_bloc_qui_ne_compile_pas_est_ecarte():
    """L'incident qui a produit ce test.

    Muse-Glimmer a échoué `cache_o1` sur ses deux essais avec le même
    `SyntaxError: invalid syntax`. Deux échecs identiques sur un modèle qui
    venait de construire un interpréteur complet : le motif accusait
    l'instrument, pas le modèle.

    Un bloc de prose encadré, ou une sortie de spécification, peut être
    plus long que le code lui-même. Retenir le plus long sans vérifier
    qu'il s'analyse fait échouer un modèle sur du texte qu'il n'a jamais
    présenté comme du code — la même erreur que l'extraction JSON gloutonne
    qui notait 0/5 des objets parfaits.
    """
    prose = "Spécification détaillée :\n" + "\n".join(
        f"  - la contrainte {i} impose un accès en temps constant" for i in range(40))
    raw = f"```\n{prose}\n```\n\nImplémentation :\n```python\n{BON}\n```"

    assert "def compter_mots" in extract_code(raw)


def test_une_cloture_manquante_ne_perd_pas_le_code():
    """Une réponse qui s'arrête en chemin laisse son ``` ouvert. Le corps
    reste exploitable ; le rendre tel quel y collerait toute la prose qui
    précède et produirait un SyntaxError d'instrument."""
    raw = f"Bien sûr, voici la fonction demandée :\n```python\n{BON}"

    assert extract_code(raw).startswith("def compter_mots")


def test_un_code_qui_ne_compile_nulle_part_est_rendu_quand_meme():
    """Sinon le message d'erreur parlerait d'un fragment choisi par défaut
    plutôt que de ce que le modèle a réellement écrit."""
    casse = "def f(:\n    return 1"

    assert extract_code(f"```python\n{casse}\n```") == casse


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


def test_une_boucle_infinie_expire_au_lieu_de_bloquer(monkeypatch):
    """Un modèle qui écrit une boucle sans fin doit coûter un essai, pas la
    campagne. C'est la raison d'être du sous-processus.

    Le délai est ramené à 2 s pour ce test. À la valeur de production
    (60 s) il prouvait exactement la même chose en trente fois plus de
    temps — et c'est *lui* que le premier garde-fou `--timeout=45` a
    attrapé, faisant passer un test lent mais sain pour le test bloqué
    qu'on cherchait. Un test long ne se distingue d'un test pendu que par
    la patience de celui qui regarde.
    """
    monkeypatch.setattr(code_bench, "EXEC_TIMEOUT_S", 2.0)
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
