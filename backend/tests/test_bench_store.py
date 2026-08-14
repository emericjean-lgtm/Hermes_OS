"""Les mesures du catalogue survivent au processus (HOS-107).

Une campagne d'échelle de contexte dure une à deux heures de GPU ; celle
des plafonds de code autant. Tout cela vivait dans des fichiers
temporaires. Ces tests pinnent ce qui doit rester vrai pour que l'onglet
Modèles affiche des mesures et non des suppositions.
"""
from __future__ import annotations

import pytest

from backend.memory.db import init_db, make_engine, make_session_factory
from backend.model_intelligence.bench_store import AXES, BenchStore


@pytest.fixture
def db(tmp_path):
    engine = make_engine(str(tmp_path / "bench.db"))
    init_db(engine)
    return make_session_factory(engine)


@pytest.fixture
def store(db):
    return BenchStore(db)


def test_une_mesure_survit_au_redemarrage(store, db):
    """Ce que la persistance existe pour garantir : un second magasin sur la
    même base — ce qu'est un redémarrage — retrouve la mesure."""
    store.record("gpt-oss:20b", "code", verdict="mythique",
                 detail={"niveaux": ["simple", "mythique"]})

    retrouve = BenchStore(db).for_model("gpt-oss:20b")

    assert retrouve["code"]["verdict"] == "mythique"
    assert retrouve["code"]["detail"]["niveaux"] == ["simple", "mythique"]


def test_une_nouvelle_campagne_remplace_l_ancienne(store):
    """Une mesure obtenue sous d'autres conditions est plus trompeuse
    qu'utile — on remplace, on n'empile pas."""
    store.record("m", "code", verdict="complexe")
    store.record("m", "code", verdict="mythique")

    axes = store.for_model("m")

    assert axes["code"]["verdict"] == "mythique"


def test_les_axes_sont_independants(store):
    store.record("gemma4:12b", "code", verdict="maitre")
    store.record("gemma4:12b", "agentique", verdict="0/3", score=0.0)

    axes = store.for_model("gemma4:12b")

    assert axes["code"]["verdict"] == "maitre"
    assert axes["agentique"]["score"] == 0.0


def test_un_axe_non_mesure_est_absent_pas_nul(store):
    """« Non mesuré » et « zéro » doivent rester distincts : gemma4 code au
    niveau maître ET fait 0/3 aux outils. Confondre les deux inventerait
    des verdicts."""
    store.record("m", "code", verdict="expert")

    axes = store.for_model("m")

    assert "vision" not in axes
    assert "agentique" not in axes


def test_un_score_de_zero_est_conserve_tel_quel(store):
    """Le piège symétrique : 0.0 est une mesure, pas une absence."""
    store.record("gemma4:12b", "agentique", verdict="0/3", score=0.0)

    assert store.for_model("gemma4:12b")["agentique"]["score"] == 0.0


def test_le_detail_brut_est_conserve(store):
    """L'onglet doit pouvoir montrer *pourquoi* un modèle plafonne — un
    chiffre sans son justificatif redevient une opinion."""
    detail = {"niveaux": [{"level": "expert", "passed": False,
                           "detail": "SyntaxError: invalid syntax"}]}
    store.record("qwen3.5:4b", "code", verdict="complexe", detail=detail)

    garde = store.for_model("qwen3.5:4b")["code"]["detail"]

    assert garde["niveaux"][0]["detail"] == "SyntaxError: invalid syntax"


def test_le_catalogue_regroupe_par_modele(store):
    store.record("a", "code", verdict="expert")
    store.record("a", "vision", verdict="3/3", score=1.0)
    store.record("b", "code", verdict="moyen")

    catalogue = {e["model"]: e for e in store.catalogue()}

    assert set(catalogue) == {"a", "b"}
    assert set(catalogue["a"]["axes"]) == {"code", "vision"}


def test_le_meilleur_sur_un_axe_est_celui_qui_a_le_meilleur_score(store):
    store.record("a", "agentique", verdict="1/3", score=0.33)
    store.record("b", "agentique", verdict="3/3", score=1.0)

    assert store.best_for("agentique") == "b"


def test_le_meilleur_ignore_les_axes_sans_score(store):
    """Le code rend un palier, pas un pourcentage : le comparer par score
    donnerait un classement inventé."""
    store.record("a", "code", verdict="mythique")

    assert store.best_for("code") is None


def test_aucun_modele_mesure_ne_donne_aucun_meilleur(store):
    assert store.best_for("agentique") is None


def test_oublier_un_modele_efface_tous_ses_axes(store):
    """Après suppression d'un modèle, ses mesures ne doivent pas hanter le
    catalogue."""
    store.record("vieux", "code", verdict="expert")
    store.record("vieux", "vision", verdict="3/3", score=1.0)

    assert store.forget("vieux") == 2
    assert store.for_model("vieux") == {}


def test_un_axe_inconnu_est_refuse(store):
    """Une faute de frappe créerait un axe fantôme que l'UI n'afficherait
    jamais, sans que rien ne le signale."""
    with pytest.raises(ValueError, match="axe inconnu"):
        store.record("m", "codee", verdict="x")


@pytest.mark.parametrize("axis", AXES)
def test_chaque_axe_declare_est_accepte(store, axis):
    store.record("m", axis, verdict="ok")

    assert axis in store.for_model("m")
