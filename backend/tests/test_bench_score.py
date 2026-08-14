"""La notation des axes mesurés (HOS-108).

Une note fausse oriente le routage vers le mauvais modèle sans que rien ne
le signale — même classe de panne qu'un vérificateur faux, un cran plus
loin dans la chaîne.
"""
from __future__ import annotations

import pytest

from backend.model_intelligence.bench_score import (
    PALIERS_CODE, meilleur_pour, note_capacite, note_taux, noter_axe, noter_modele,
)


# ── taux de réussite ─────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict,attendu", [
    ("3/3", 100), ("0/3", 0), ("2/3", 67), ("5/6", 83), ("1/3", 33),
])
def test_un_taux_devient_un_pourcentage(verdict, attendu):
    assert note_taux(verdict) == attendu


def test_un_verdict_non_numerique_ne_donne_pas_de_note():
    assert note_taux("mythique") is None


# ── paliers de code ──────────────────────────────────────────────────────

def test_les_paliers_de_code_sont_croissants():
    valeurs = list(PALIERS_CODE.values())
    assert valeurs == sorted(valeurs)


def test_l_echelle_a_neuf_niveaux_ne_va_pas_jusqu_a_cent():
    """Trois modèles sur dix épuisent l'échelle. Un sommet atteint par
    plusieurs candidats ne les classe plus — les points restants sont donc
    réservés aux épreuves de départage, au-delà de `mythique`."""
    assert PALIERS_CODE["mythique"] == 64


def test_le_departage_mene_a_cent():
    """Six épreuves à six points : 64 + 36. La note pleine exige d'avoir
    passé les six, pas seulement d'avoir fini l'échelle."""
    detail = {"extremes": [{"reussi": True}] * 3, "abyssales": [{"reussi": True}] * 3}

    assert noter_axe("code", {"verdict": "mythique", "detail": detail}) == 100


def test_un_modele_au_sommet_de_l_echelle_sans_departage_n_a_pas_cent():
    """L'incident que cette échelle empêche : gpt-oss, muse-glimmer et
    qwen3.6 affichaient tous les trois 100/100 en code, et le routage
    n'avait donc aucune raison de préférer l'un à l'autre. Mesuré ensuite :
    3/3, 2/3 et 2/3 aux épreuves extrêmes."""
    assert noter_axe("code", {"verdict": "mythique"}) == 64


def test_les_epreuves_reussies_se_comptent_sur_les_deux_series():
    detail = {"extremes": [{"reussi": True}, {"reussi": True}, {"reussi": False}],
              "abyssales": [{"reussi": True}, {"reussi": False}, {"reussi": False}]}

    assert noter_axe("code", {"verdict": "mythique", "detail": detail}) == 64 + 18


def test_le_departage_ne_rattrape_pas_un_palier_faible():
    """La note reste bornée : un modèle qui plafonne à `expert` et
    réussirait par accident une épreuve extrême ne doit pas dépasser un
    modèle qui a réellement gravi l'échelle."""
    detail = {"extremes": [{"reussi": True}]}

    assert noter_axe("code", {"verdict": "expert", "detail": detail}) == 34
    assert noter_axe("code", {"verdict": "expert", "detail": detail}) < PALIERS_CODE["maitre"] + 6


def test_la_progression_des_paliers_est_acceleree():
    """Dix modèles sur dix passent `simple`, trois atteignent `mythique`.
    Une échelle linéaire dirait que ces deux marches se valent — le routage
    croirait alors que tous les modèles se ressemblent."""
    bas = PALIERS_CODE["moyen"] - PALIERS_CODE["simple"]
    haut = PALIERS_CODE["mythique"] - PALIERS_CODE["maitre"]

    assert haut > bas


def test_un_palier_inconnu_ne_donne_pas_de_note():
    assert noter_axe("code", {"verdict": "inexistant"}) is None


# ── capacité ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("contexte,attendu", [
    (262144, 100), (131072, 75), (65536, 50), (40960, 25),
])
def test_le_contexte_servi_donne_la_note(contexte, attendu):
    assert note_capacite(contexte) == attendu


def test_un_modele_sous_le_plancher_garde_une_note_non_nulle():
    """40 960 est sous les 64k requis, mais le modèle existe et fonctionne —
    zéro serait un verdict, pas une mesure."""
    assert note_capacite(40960) == 25


def test_un_debordement_cpu_annule_la_note():
    """Un modèle qui déborde répond sans erreur, plusieurs fois plus
    lentement et de façon erratique. Mesuré : Q3_K_XL à 21 % de débordement
    tombait de 38 à 13 tok/s. Ce n'est pas graduel, c'est disqualifiant."""
    assert note_capacite(262144, debordement=0.21) == 0


def test_la_capacite_se_lit_dans_le_detail_des_paliers():
    mesure = {"verdict": "128k", "detail": {"tiers": [
        {"num_ctx": 65536, "context_length": 65536, "cpu_offload_ratio": 0.0},
        {"num_ctx": 131072, "context_length": 131072, "cpu_offload_ratio": 0.0},
        {"num_ctx": 262144, "context_length": 131072, "cpu_offload_ratio": 0.17},
    ]}}

    assert noter_axe("capacite", mesure) == 75


def test_la_capacite_retombe_sur_le_verdict_sans_detail():
    assert noter_axe("capacite", {"verdict": "256k", "detail": {}}) == 100


# ── un axe non mesuré n'est pas un zéro ──────────────────────────────────

def test_un_axe_absent_ne_donne_pas_de_note():
    """None et 0 doivent rester distincts : un modèle jamais teste passerait
    sinon pour mauvais dans l'onglet."""
    assert noter_axe("vision", {}) is None


def test_un_zero_mesure_reste_un_zero():
    assert noter_axe("agentique", {"verdict": "0/3"}) == 0


def test_noter_un_modele_conserve_les_axes_non_mesurables():
    notes = noter_modele({"code": {"verdict": "maitre"},
                          "vision": {"verdict": "3/3"},
                          "agentique": {"verdict": "bizarre"}})

    assert notes == {"code": 36, "vision": 100, "agentique": None}


# ── raisonnement ─────────────────────────────────────────────────────────

def test_le_raisonnement_se_note_comme_un_taux():
    """L'axe existe parce que le plafond de code ne prédit pas la déduction.

    Artificial Analysis place Qwen3.6-27B à 38 d'indice d'intelligence
    contre 15 pour gpt-oss-20b, alors que les deux atteignent `mythique` en
    code. Aucun axe existant ne touchait cette dimension.
    """
    assert noter_axe("raisonnement", {"verdict": "4/4"}) == 100
    assert noter_axe("raisonnement", {"verdict": "1/4"}) == 25


def test_le_raisonnement_est_un_axe_du_catalogue():
    """Sans quoi ``BenchStore.record`` refuse la mesure et une campagne
    d'une heure finit dans un fichier temporaire."""
    from backend.model_intelligence.bench_store import AXES

    assert "raisonnement" in AXES


# ── candidats pour le routage ────────────────────────────────────────────

def test_les_candidats_sont_classes_du_meilleur_au_moins_bon():
    catalogue = [
        {"model": "a", "axes": {"code": {"verdict": "expert"}}},
        {"model": "b", "axes": {"code": {"verdict": "mythique"}}},
        {"model": "c", "axes": {"code": {"verdict": "moyen"}}},
    ]

    assert meilleur_pour(catalogue, "code") == [("b", 64), ("a", 28), ("c", 12)]


def test_un_modele_sans_mesure_sur_l_axe_est_ecarte():
    catalogue = [{"model": "a", "axes": {"vision": {"verdict": "3/3"}}},
                 {"model": "b", "axes": {"code": {"verdict": "expert"}}}]

    assert [m for m, _ in meilleur_pour(catalogue, "code")] == ["b"]


def test_le_seuil_ecarte_les_modeles_trop_faibles():
    """Le routage demande « qui peut faire du code de niveau expert » et non
    « qui sait coder » — un modèle à 20 ne doit pas figurer dans la réponse."""
    catalogue = [{"model": "a", "axes": {"code": {"verdict": "moyen"}}},
                 {"model": "b", "axes": {"code": {"verdict": "mythique"}}}]

    assert [m for m, _ in meilleur_pour(catalogue, "code", note_minimale=44)] == ["b"]


def test_aucun_candidat_donne_une_liste_vide():
    assert meilleur_pour([], "code") == []
