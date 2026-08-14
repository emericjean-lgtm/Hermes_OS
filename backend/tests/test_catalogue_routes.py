"""Le catalogue mesuré, exposé à l'onglet Modèles (HOS-108).

Ces routes ne rendent que des mesures réelles — distinctes des routes
voisines, qui exposent les heuristiques du ModelProfiler. La distinction
compte : l'onglet doit pouvoir dire « mesuré le 14 août sous Ollama
0.32.9 » plutôt que « estimé ».
"""
from __future__ import annotations

import pytest

from backend.memory.db import init_db, make_engine, make_session_factory
from backend.model_intelligence import routes
from backend.model_intelligence.bench_store import BenchStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = make_engine(str(tmp_path / "cat.db"))
    init_db(engine)
    fabrique = make_session_factory(engine)
    magasin = BenchStore(fabrique)
    monkeypatch.setattr("backend.model_intelligence.bench_store.BenchStore",
                        lambda *a, **k: magasin)
    return magasin


def test_le_catalogue_porte_les_notes_a_cote_des_verdicts(store):
    store.record("gpt-oss-20b-64k", "code", verdict="mythique",
                 detail={"niveaux": []})
    store.record("gpt-oss-20b-64k", "agentique", verdict="3/3", score=1.0)

    payload = routes.handle_get_catalogue()

    entree = next(e for e in payload["models"] if e["model"] == "gpt-oss-20b-64k")
    # 64 et non 100 : le palier `mythique` est le sommet de l'échelle à
    # neuf niveaux, pas de la compétence — les 36 points restants se
    # gagnent aux épreuves de départage, absentes de ce détail.
    assert entree["notes"]["code"] == 64
    assert entree["notes"]["agentique"] == 100
    assert entree["axes"]["code"]["verdict"] == "mythique"


def test_un_axe_non_mesure_rend_none_et_non_zero(store):
    """Un modèle jamais testé sur un axe passerait sinon pour mauvais."""
    store.record("m", "code", verdict="expert")

    entree = routes.handle_get_catalogue()["models"][0]

    assert "vision" not in entree["notes"]
    assert entree["notes"]["code"] == 28


def test_un_zero_mesure_est_conserve(store):
    """Le piège symétrique : 0 est une mesure, pas une absence."""
    store.record("m", "agentique", verdict="0/3", score=0.0)

    assert routes.handle_get_catalogue()["models"][0]["notes"]["agentique"] == 0


def test_le_detail_brut_accompagne_la_note(store):
    """L'onglet doit pouvoir montrer pourquoi un modèle plafonne."""
    store.record("m", "code", verdict="complexe", detail={
        "niveaux": [{"level": "expert", "passed": False,
                     "detail": "SyntaxError: invalid syntax"}]})

    entree = routes.handle_get_catalogue()["models"][0]

    assert entree["axes"]["code"]["detail"]["niveaux"][0]["detail"].startswith("SyntaxError")


def test_les_axes_du_catalogue_sont_annonces(store):
    payload = routes.handle_get_catalogue()

    assert "code" in payload["axes"] and "long_contexte" in payload["axes"]


def test_un_catalogue_vide_ne_casse_pas(store):
    payload = routes.handle_get_catalogue()

    assert payload["success"] is True and payload["total"] == 0


# ── candidats pour le routage ────────────────────────────────────────────

def test_les_candidats_sont_classes(store):
    store.record("fort", "code", verdict="mythique")
    store.record("moyen", "code", verdict="expert")
    store.record("faible", "code", verdict="moyen")

    noms = [c["model"] for c in routes.handle_get_candidats("code")["candidats"]]

    assert noms == ["fort", "moyen", "faible"]


def test_le_seuil_ecarte_les_trop_faibles(store):
    """Le routage demande « qui peut faire du niveau expert », pas « qui
    sait coder »."""
    store.record("fort", "code", verdict="mythique")
    store.record("faible", "code", verdict="moyen")

    resultat = routes.handle_get_candidats("code", note_minimale=44)

    assert [c["model"] for c in resultat["candidats"]] == ["fort"]


def test_aucun_candidat_rend_une_liste_vide_pas_une_erreur(store):
    assert routes.handle_get_candidats("vision")["candidats"] == []


def test_les_routes_sont_montees():
    chemins = [r.path for r in routes.router.routes]

    assert "/models/catalogue" in chemins
    assert "/models/catalogue/candidats" in chemins


def test_catalogue_precede_le_parametre_dynamique():
    """« catalogue » ne doit pas être capturé comme un identifiant de
    modèle — même piège que /autonomous/goals face à /{goal_id}."""
    chemins = [r.path for r in routes.router.routes]
    dynamiques = [c for c in chemins if "{" in c]

    for dyn in dynamiques:
        if dyn.count("/") == 2:  # /models/{quelque_chose}
            assert chemins.index("/models/catalogue") < chemins.index(dyn)
