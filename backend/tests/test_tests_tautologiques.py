"""Une suite verte au-dessus d'une protection inerte (HOS-153).

L'incident nomme ici est le seul de la liste que l'assistant a commis
lui-meme : les tests du garde-fou de workspace passaient `args=...` a un
hook qui lit `tool_input`. Six tests verts, une protection qui n'a jamais
rien refuse, et rien pour le signaler — un test vert ne se relit pas.

La moitie de ces tests porte sur ce que le garde **ne** signale **pas** :
ce projet a mesure que cinq de ses huit defauts d'instrumentation
produisaient de faux echecs. Un garde qui refuserait des tests legitimes
couterait plus cher que celui qu'il remplace.
"""
from __future__ import annotations

from backend.mission import programme, tests_tautologiques as tauto


def _raisons(source: str) -> list[str]:
    return [r for _, _, r in tauto.fautes_du_source(source)]


# -- ce qui doit etre signale -----------------------------------------

def test_une_constante_vraie_est_signalee() -> None:
    assert _raisons("def test_a():\n    assert True\n")


def test_un_terme_compare_a_lui_meme_est_signale() -> None:
    src = "def test_a():\n    r = calcule()\n    assert r == r\n"
    assert _raisons(src)


def test_deux_constantes_comparees_sont_signalees() -> None:
    assert _raisons("def test_a():\n    assert 1 == 1\n")


def test_la_negation_d_une_constante_fausse_est_signalee() -> None:
    assert _raisons("def test_a():\n    assert not False\n")


def test_une_liste_litterale_non_vide_est_signalee() -> None:
    assert _raisons("def test_a():\n    assert ['x']\n")


# -- ce qui ne doit **pas** l'etre ------------------------------------

def test_une_assertion_reelle_est_laissee_tranquille() -> None:
    src = "def test_a():\n    assert calcule(2) == 4\n"
    assert _raisons(src) == []


def test_un_test_sans_assertion_est_laisse_tranquille() -> None:
    """`def test_import(): import monmodule` echoue si l'import leve.

    Le signaler serait le faux echec type : un test legitime refuse au
    motif qu'il n'a pas la forme attendue.
    """
    assert _raisons("def test_import():\n    import os\n") == []


def test_deux_appels_identiques_sont_laisses_tranquilles() -> None:
    """`f() == f()` peut echouer — c'est meme souvent tout l'interet."""
    src = "def test_a():\n    assert tirage() == tirage()\n"
    assert _raisons(src) == []


def test_une_constante_hors_d_un_test_est_laissee_tranquille() -> None:
    """`assert True` dans du code de production est une garde d'invariant."""
    src = "def charge(x):\n    assert True\n    return x\n"
    assert _raisons(src) == []


def test_un_fichier_qui_ne_compile_pas_ne_leve_pas() -> None:
    """Un echec deja visible ne releve pas de ce garde."""
    assert tauto.fautes_du_source("def test_a(:\n") == []


# -- l'incident, de bout en bout --------------------------------------

def test_le_verdict_nomme_le_fichier_la_ligne_et_la_fonction(tmp_path) -> None:
    (tmp_path / "test_garde.py").write_text(
        "def test_le_hook_refuse():\n"
        "    hook(args={'path': '/hors/workspace'})\n"
        "    assert True\n", encoding="utf-8")

    faute = tauto.verdict(str(tmp_path))

    assert faute is not None
    assert faute["fichier"] == "test_garde.py"
    assert faute["ligne"] == 3
    assert faute["fonction"] == "test_le_hook_refuse"


def test_seuls_les_fichiers_de_test_sont_inspectes(tmp_path) -> None:
    (tmp_path / "outils.py").write_text(
        "def test_interne():\n    assert True\n", encoding="utf-8")

    assert tauto.verdict(str(tmp_path)) is None


def test_une_section_dont_les_tests_ne_peuvent_pas_rougir_est_bloquante() -> None:
    """Le point du garde : cette section ne doit pas passer pour faite."""
    bloque, raison = programme.bloquant({
        "created": ["test_x.py"],
        "tests": {"ran": True, "passed": True},
        "test_tautologique": {"fichier": "test_x.py", "ligne": 3,
                              "fonction": "test_a",
                              "raison": "la condition est une constante vraie"},
    })

    assert bloque
    assert "ne peut pas echouer" in raison
    assert "test_x.py:3" in raison


def test_le_brief_de_reparation_dit_quoi_faire() -> None:
    """Sans l'erreur exacte, la seconde passe repart aussi aveugle."""
    brief = programme.diagnostic({
        "test_tautologique": {"fichier": "test_x.py", "ligne": 3,
                              "fonction": "test_a", "raison": "constante"},
    }, "peu importe")

    assert "test_x.py:3" in brief
    assert "test_a()" in brief
    # Il doit demander la preuve, pas seulement signaler le defaut.
    assert "rougit" in brief
