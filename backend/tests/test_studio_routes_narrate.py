"""POST /studio/narrate (HOS-196).

La route est un passe-plat vers `narration.synthetiser` — déjà couvert en
détail par `test_studio_narration.py`. Ce fichier teste seulement la
couche route : ce qu'elle refuse avant d'appeler la synthèse, et ce
qu'elle fait du champ `dossier` optionnel, que `synthetiser` lui-même ne
connaît pas (c'est la route qui décide du chemin par défaut).
"""

from __future__ import annotations

import backend.studio.narration as narration_mod
from backend.studio import routes
from backend.studio.narration import Narration, SegmentNarre


def test_sans_lignes_ne_synthetise_rien(monkeypatch):
    appele = []
    monkeypatch.setattr(narration_mod, "synthetiser",
                        lambda *a, **k: appele.append(1) or Narration())

    reponse = routes.narrer({})

    assert reponse["success"] is False
    assert not appele


def test_des_lignes_sans_aucun_texte_sont_refusees(monkeypatch):
    appele = []
    monkeypatch.setattr(narration_mod, "synthetiser",
                        lambda *a, **k: appele.append(1) or Narration())

    reponse = routes.narrer({"lignes": [{"id": "a", "texte": "   "}]})

    assert reponse["success"] is False
    assert not appele


def test_sans_dossier_explicite_la_route_en_horodate_un(monkeypatch):
    vus = {}

    def fausse_synthese(textes, dossier, **k):
        vus["dossier"] = dossier
        return Narration(segments=[SegmentNarre(identifiant="a", chemin="a.wav",
                                                 duree_s=1.2)])

    monkeypatch.setattr(narration_mod, "synthetiser", fausse_synthese)

    reponse = routes.narrer({"lignes": [{"id": "a", "texte": "Bonsoir."}]})

    assert reponse["success"] is True
    assert reponse["dossier"] == vus["dossier"]
    # Sous le dossier de base de la route, pas un chemin choisi au hasard.
    assert vus["dossier"].startswith(routes.DOSSIER_NARRATION)


def test_un_dossier_fourni_par_lappelant_est_respecte_tel_quel(monkeypatch, tmp_path):
    vus = {}

    def fausse_synthese(textes, dossier, **k):
        vus["dossier"] = dossier
        return Narration(segments=[SegmentNarre(identifiant="a", chemin="a.wav")])

    monkeypatch.setattr(narration_mod, "synthetiser", fausse_synthese)

    cible = str(tmp_path / "ma_narration")
    reponse = routes.narrer({"lignes": [{"id": "a", "texte": "Bonsoir."}],
                             "dossier": cible})

    assert reponse["dossier"] == cible
    assert vus["dossier"] == cible


def test_un_segment_en_echec_se_lit_dans_la_reponse_meme_si_reussie_est_fausse(monkeypatch):
    monkeypatch.setattr(
        narration_mod, "synthetiser",
        lambda *a, **k: Narration(segments=[
            SegmentNarre(identifiant="a", chemin="a.wav", duree_s=1.0),
            SegmentNarre(identifiant="b", erreur="voix introuvable"),
        ]))

    reponse = routes.narrer({"lignes": [
        {"id": "a", "texte": "Bonsoir."}, {"id": "b", "texte": "Et voici."},
    ]})

    assert reponse["success"] is False  # Narration.reussie exige tous les segments.
    assert reponse["segments"][0]["reussi"] is True
    assert reponse["segments"][1]["reussi"] is False
    assert reponse["segments"][1]["erreur"] == "voix introuvable"


def test_chatterbox_indisponible_est_rapporte_pas_leve(monkeypatch):
    def leve(*a, **k):
        raise narration_mod.ChatterboxIndisponible("Chatterbox n'est pas installé")

    monkeypatch.setattr(narration_mod, "synthetiser", leve)

    reponse = routes.narrer({"lignes": [{"id": "a", "texte": "Bonsoir."}]})

    assert reponse["success"] is False
    assert reponse["raison"] == "chatterbox_absent"
